# Logs and alarms. The app also emails its own alerts (ALERT_EMAIL, D-109: storage or Redis down,
# recordings stuck or failed, calls waiting for a person); these alarms cover the machine around it.
#
# The log group names are fixed: the server's files use them (deploy/aws/env.example
# AWS_LOG_GROUP, deploy/aws/cloudwatch-agent.json). The CloudWatch agent publishes the disk and
# memory figures under the namespace "CCP".

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ccp/app"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "operations" {
  name              = "/ccp/operations"
  retention_in_days = var.log_retention_days
}

resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

resource "aws_sns_topic_subscription" "alarm_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "server_status" {
  alarm_name          = "${var.name}-server-status-check"
  alarm_description   = "The server failed an EC2 status check (hardware, network or the system itself)."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = aws_instance.server.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "server_cpu" {
  alarm_name          = "${var.name}-server-cpu-high"
  alarm_description   = "Server CPU above 85% for 15 minutes (a deploy's build takes a few minutes; this is longer)."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = aws_instance.server.id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 85
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "server_disk" {
  alarm_name          = "${var.name}-server-disk-80"
  alarm_description   = "Server disk more than 80% full (Docker images, build cache, work files)."
  namespace           = "CCP"
  metric_name         = "disk_used_percent"
  dimensions          = { InstanceId = aws_instance.server.id }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "db_storage" {
  alarm_name          = "${var.name}-db-free-storage-low"
  alarm_description   = "Database disk has less than 2 GB free (it grows by itself up to db_max_storage_gb)."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.db.identifier }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 2147483648
  comparison_operator = "LessThanThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# deploy/aws/deploy.sh and backup.sh write "deploy: FAILED ..." / "backup: FAILED ..." to
# /var/log/ccp/operations.log, which the CloudWatch agent sends to /ccp/operations.
resource "aws_cloudwatch_log_metric_filter" "ops_failed" {
  name           = "${var.name}-deploy-or-backup-failed"
  log_group_name = aws_cloudwatch_log_group.operations.name
  pattern        = "FAILED"

  metric_transformation {
    name      = "OpsFailed"
    namespace = "CCP"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "ops_failed" {
  alarm_name          = "${var.name}-deploy-or-backup-failed"
  alarm_description   = "A deploy or the daily backup failed. Read /var/log/ccp/operations.log or the /ccp/operations log group."
  namespace           = "CCP"
  metric_name         = "OpsFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}
