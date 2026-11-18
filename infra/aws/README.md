# AWS resources (Terraform, D-132)

Makes everything Conversation Collection needs in the client's AWS account, region ap-south-1
(Mumbai). The step-by-step procedure, the move from Render and daily running are in
`docs/DEPLOYMENT_AWS.md`; the server's own files are in `deploy/aws/`.

Status: `terraform fmt -check` and `terraform validate` pass (Terraform 1.17.2, AWS provider
6.73.0, 2026-11-18). **Never applied**: nothing has been created in AWS yet.

## What it makes

| Resource | Details |
|---|---|
| Network | The account's **default VPC** (no NAT gateway or VPC of our own to pay for or look after). Security group `ccp-server`: ports 80 and 443 from Cloudflare's ranges only, no SSH. `ccp-db`: PostgreSQL from `ccp-server` only |
| Server | EC2 `ccp-server`: t3.medium, Ubuntu 24.04 LTS, 40 GB gp3 encrypted, IMDSv2 only, termination protection; an Elastic IP. First boot runs `deploy/aws/bootstrap.sh` |
| Server role | Session Manager (`AmazonSSMManagedInstanceCore`), CloudWatch agent and container logs (`CloudWatchAgentServerPolicy`), the recordings bucket (read, write, delete; not "delete a kept version") |
| Admin access | Group `ccp-admins` with policy `ccp-admin-session`: a shell on this server through Session Manager, nothing else. Users from `admin_iam_users` join it |
| Database | RDS PostgreSQL 16 `ccp-db`: db.t4g.small, 20 GB gp3 encrypted (grows to 100 GB), automated backups 7 days, not public, deletion protection, final snapshot on delete |
| Files | S3 bucket `ccp-recordings-<account id>`: private (Block Public Access, ACLs off), SSE-S3, HTTPS only, versioning with deleted versions gone after 30 days, unfinished uploads removed after 7 days |
| Logs | CloudWatch Logs `/ccp/app` (containers) and `/ccp/operations` (deploys and backups), 30 days |
| Alarms | Email (SNS topic `ccp-alarms`) on: server status check failed, CPU above 85% for 15 minutes, disk above 80%, database free space under 2 GB, a deploy or backup FAILED |

## Variables

Required: `alarm_email`. Usually also `admin_iam_users`. Others have defaults
(`variables.tf`): `region`, `availability_zone`, `instance_type`, `root_volume_gb`,
`db_instance_class`, `db_storage_gb`, `db_max_storage_gb`, `db_backup_days`, `web_ingress_cidrs`
(Cloudflare's ranges; `["0.0.0.0/0"]` without Cloudflare), `recordings_versioning`,
`recordings_noncurrent_days`, `log_retention_days`, `domain`, `repo_url`, `repo_branch`,
`storage_user_fallback`.

## Outputs

`elastic_ip`, `rds_endpoint`, `bucket_name`, `db_password` (sensitive), `instance_id`,
`shell_command`, `log_group_app`, `env_lines` (lines for the server's `.env`), `dns_record`,
`admin_session_policy_arn`.

## State

Local state (`terraform.tfstate` here, never committed): simplest for one operator, but it holds
the database password, so keep this folder private and back the file up. For several operators, an
S3 bucket with versioning and encryption as a `backend "s3"` (with `use_lockfile = true`) keeps one
shared copy; add it later with `terraform init -migrate-state`.

## Commands

```sh
cd infra/aws
cp terraform.tfvars.example terraform.tfvars    # fill in
terraform init
terraform plan -out ccp.tfplan
terraform apply ccp.tfplan
terraform output                                # elastic_ip, rds_endpoint, bucket_name, ...
terraform output -raw db_password               # once, for the server's .env
```

Changes later: edit `terraform.tfvars` or the files, then `plan` and `apply` again. A newer
Ubuntu image or a changed `bootstrap.sh` never replaces the server (`ignore_changes`).

Taking it all down is deliberately hard: the server has termination protection, the database has
deletion protection, and the bucket refuses to be deleted while it has files. Turn those off one by
one, on purpose.
