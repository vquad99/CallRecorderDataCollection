# The server: one EC2 instance in the account's default VPC, an Elastic IP, its role, and the
# shell access for admins (Session Manager; no SSH port).

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# The default VPC: public subnets in every zone, nothing to pay for (no NAT). An account without
# one: `aws ec2 create-default-vpc --region ap-south-1`.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnet" "server" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

# Canonical's current Ubuntu 24.04 LTS image. ignore_changes below: a newer image never replaces
# the running server.
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

locals {
  arn_prefix = "arn:${data.aws_partition.current.partition}"
}

# --- network rules

resource "aws_security_group" "server" {
  name        = "${var.name}-server"
  description = "Conversation Collection server: web from Cloudflare only, no SSH"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each = { for pair in setproduct(var.web_ingress_cidrs, [80, 443]) : "${pair[0]}:${pair[1]}" => pair }

  security_group_id = aws_security_group.server.id
  description       = "web"
  cidr_ipv4         = each.value[0]
  from_port         = each.value[1]
  to_port           = each.value[1]
  ip_protocol       = "tcp"
}

# Out: GitHub, Docker Hub, Ubuntu updates, Resend (SMTP 587), TxContact, S3, CloudWatch, SSM, RDS.
resource "aws_vpc_security_group_egress_rule" "server_all" {
  security_group_id = aws_security_group.server.id
  description       = "all outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# --- the server's role: Session Manager, CloudWatch agent and container logs, the recordings bucket

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "server" {
  name               = "${var.name}-server"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "${local.arn_prefix}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.server.name
  policy_arn = "${local.arn_prefix}:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy" "recordings" {
  name   = "recordings-bucket"
  role   = aws_iam_role.server.id
  policy = data.aws_iam_policy_document.recordings_access.json
}

resource "aws_iam_instance_profile" "server" {
  name = "${var.name}-server"
  role = aws_iam_role.server.name
}

# --- the server

resource "aws_instance" "server" {
  ami                     = data.aws_ssm_parameter.ubuntu.insecure_value
  instance_type           = var.instance_type
  subnet_id               = data.aws_subnet.server.id
  vpc_security_group_ids  = [aws_security_group.server.id]
  iam_instance_profile    = aws_iam_instance_profile.server.name
  disable_api_termination = true

  # First boot: saves and runs deploy/aws/bootstrap.sh (Docker, git, CloudWatch agent, the ccp
  # user and its deploy key).
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url      = var.repo_url
    repo_branch   = var.repo_branch
    bootstrap_b64 = filebase64("${path.module}/../../deploy/aws/bootstrap.sh")
  })

  # IMDSv2 only. Hop limit 2: the containers (one network hop further) use the role too.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  # Image builds and audio processing burst above the t3 baseline; "unlimited" never slows them
  # down, at a small extra charge when the average stays high.
  credit_specification {
    cpu_credits = "unlimited"
  }

  tags = {
    Name = "${var.name}-server"
  }

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "server" {
  domain   = "vpc"
  instance = aws_instance.server.id

  tags = {
    Name = "${var.name}-server"
  }
}

# --- admins: a shell on this server through Session Manager, nothing else

data "aws_iam_policy_document" "admin_session" {
  statement {
    sid     = "ShellOnThisServer"
    actions = ["ssm:StartSession"]
    resources = [
      aws_instance.server.arn,
      "${local.arn_prefix}:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:document/SSM-SessionManagerRunShell",
    ]
    condition {
      test     = "BoolIfExists"
      variable = "ssm:SessionDocumentAccessCheck"
      values   = ["true"]
    }
  }

  statement {
    sid       = "OwnSessions"
    actions   = ["ssm:TerminateSession", "ssm:ResumeSession"]
    resources = ["${local.arn_prefix}:ssm:*:*:session/$${aws:userid}-*", "${local.arn_prefix}:ssm:*:*:session/$${aws:username}-*"]
  }

  statement {
    sid = "SeeTheServerInTheConsole"
    actions = [
      "ssm:DescribeSessions",
      "ssm:GetConnectionStatus",
      "ssm:DescribeInstanceInformation",
      "ssm:DescribeInstanceProperties",
      "ec2:DescribeInstances",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "admin_session" {
  name        = "${var.name}-admin-session"
  description = "Open a shell on the Conversation Collection server with Session Manager"
  policy      = data.aws_iam_policy_document.admin_session.json
}

resource "aws_iam_group" "admins" {
  name = "${var.name}-admins"
}

resource "aws_iam_group_policy_attachment" "admins" {
  group      = aws_iam_group.admins.name
  policy_arn = aws_iam_policy.admin_session.arn
}

resource "aws_iam_user_group_membership" "admins" {
  for_each = toset(var.admin_iam_users)

  user   = each.value
  groups = [aws_iam_group.admins.name]
}
