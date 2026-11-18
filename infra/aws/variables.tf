variable "region" {
  description = "AWS region. Mumbai, close to the users in India."
  type        = string
  default     = "ap-south-1"
}

variable "availability_zone" {
  description = "Zone for the server and the database (the same zone: no cross-zone traffic)."
  type        = string
  default     = "ap-south-1a"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "ccp"
}

variable "domain" {
  description = "The site's address. Used in the outputs (DNS record to make)."
  type        = string
  default     = "dubdesk.live"
}

variable "alarm_email" {
  description = "Where CloudWatch alarms are emailed. AWS sends a confirmation link first."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alarm_email))
    error_message = "alarm_email must be an email address."
  }
}

variable "admin_iam_users" {
  description = "IAM user names that may open a shell on the server (Session Manager). For roles or IAM Identity Center, attach the output admin_session_policy_arn instead."
  type        = list(string)
  default     = []
}

variable "instance_type" {
  description = "EC2 size for the server (web, API, worker, Redis, image builds)."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_gb" {
  description = "Server disk (encrypted gp3): system, Docker images, build cache, Redis, work files."
  type        = number
  default     = 40
}

variable "db_instance_class" {
  description = "RDS size."
  type        = string
  default     = "db.t4g.small"
}

variable "db_storage_gb" {
  description = "RDS disk at the start (gp3, encrypted)."
  type        = number
  default     = 20
}

variable "db_max_storage_gb" {
  description = "RDS grows its disk by itself up to this size."
  type        = number
  default     = 100
}

variable "db_backup_days" {
  description = "Days of RDS automated backups (restore to any minute in that time)."
  type        = number
  default     = 7
}

# Cloudflare's IPv4 ranges (https://www.cloudflare.com/ips-v4, read 2026-11-18; the same list is in
# deploy/aws/Caddyfile). Only Cloudflare can reach ports 80 and 443. Without Cloudflare in front,
# set ["0.0.0.0/0"].
variable "web_ingress_cidrs" {
  description = "Addresses allowed to reach ports 80 and 443."
  type        = list(string)
  default = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
  ]
}

variable "recordings_versioning" {
  description = "Keep a deleted or overwritten file for recordings_noncurrent_days before it is gone for good."
  type        = bool
  default     = true
}

variable "recordings_noncurrent_days" {
  description = "Days a deleted or overwritten file can still be brought back (versioning on)."
  type        = number
  default     = 30

  validation {
    condition     = var.recordings_noncurrent_days >= 1
    error_message = "recordings_noncurrent_days must be 1 or more."
  }
}

variable "log_retention_days" {
  description = "Days CloudWatch keeps container and deploy logs."
  type        = number
  default     = 30
}

variable "repo_url" {
  description = "Git address the server clones with its read-only deploy key."
  type        = string
  default     = "git@github.com:vquad99/CallRecorderDataCollection.git"
}

variable "repo_branch" {
  description = "Branch the server deploys."
  type        = string
  default     = "main"
}

variable "storage_user_fallback" {
  description = "Also make an IAM user with the server's bucket rights, for keys in .env on a host without the server's role (normally false: the app uses the role, docs/DEPLOYMENT_AWS.md section 9). Keys are made by hand, so they never enter the state."
  type        = bool
  default     = false
}
