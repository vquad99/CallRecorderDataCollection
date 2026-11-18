# Conversation Collection on AWS (D-132): one EC2 server, RDS PostgreSQL, an S3 bucket, logs and
# alarms, in the client's account in Mumbai. See README.md here and docs/DEPLOYMENT_AWS.md.
#
# State: local (terraform.tfstate in this folder, on the operator's computer). It holds the database
# password: keep it private and backed up. See README.md for moving it to an S3 bucket.

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "conversation-collection"
      ManagedBy = "terraform"
    }
  }
}
