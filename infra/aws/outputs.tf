output "elastic_ip" {
  description = "The server's fixed public address. Cloudflare: A record for the domain, proxied."
  value       = aws_eip.server.public_ip
}

output "instance_id" {
  description = "The server."
  value       = aws_instance.server.id
}

output "shell_command" {
  description = "Open a shell on the server (or EC2 console > the instance > Connect > Session Manager)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.server.id}"
}

output "rds_endpoint" {
  description = "Database host name for DB_HOST in the server's .env."
  value       = aws_db_instance.db.address
}

output "db_password" {
  description = "Database password for POSTGRES_PASSWORD in the server's .env: terraform output -raw db_password"
  value       = random_password.db.result
  sensitive   = true
}

output "bucket_name" {
  description = "Recordings bucket for STORAGE_BUCKET in the server's .env."
  value       = aws_s3_bucket.recordings.bucket
}

output "log_group_app" {
  description = "Container logs (AWS_LOG_GROUP in the server's .env)."
  value       = aws_cloudwatch_log_group.app.name
}

output "admin_session_policy_arn" {
  description = "Attach to a role or IAM Identity Center permission set that should open a shell on the server."
  value       = aws_iam_policy.admin_session.arn
}

output "env_lines" {
  description = "Lines for deploy/aws/.env on the server (the password comes from db_password)."
  value       = <<-EOT
    DB_HOST=${aws_db_instance.db.address}
    STORAGE_ENDPOINT_URL=https://s3.${var.region}.amazonaws.com
    STORAGE_REGION=${var.region}
    STORAGE_BUCKET=${aws_s3_bucket.recordings.bucket}
    AWS_LOG_GROUP=${aws_cloudwatch_log_group.app.name}
    AWS_REGION=${var.region}
  EOT
}

output "dns_record" {
  description = "The record to change at the move."
  value       = "Cloudflare DNS: A ${var.domain} -> ${aws_eip.server.public_ip}, Proxied (orange cloud)"
}
