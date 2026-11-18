# The database: RDS PostgreSQL 16, single zone, not public, reachable only from the server.
# AWS patches it (minor versions) and keeps automated backups (restore to any minute in the last
# db_backup_days days). Connections must use TLS (rds.force_ssl is on by default from PostgreSQL 15).

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "Conversation Collection database: PostgreSQL from the server only"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_server" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL from the server"
  referenced_security_group_id = aws_security_group.server.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_subnet_group" "db" {
  name       = "${var.name}-db"
  subnet_ids = data.aws_subnets.default.ids
}

# Letters and digits only: safe inside a database URL. It is in the Terraform state (keep the state
# private); `terraform output -raw db_password` shows it once for the server's .env.
resource "random_password" "db" {
  length  = 40
  special = false
}

resource "aws_db_instance" "db" {
  identifier     = "${var.name}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_storage_gb
  max_allocated_storage = var.db_max_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "ccp"
  username = "ccp"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  availability_zone      = var.availability_zone
  publicly_accessible    = false
  multi_az               = false

  # 01:30-02:00 and Sunday 02:30-03:30 India time: the quietest hours.
  backup_retention_period    = var.db_backup_days
  backup_window              = "20:00-20:30"
  maintenance_window         = "sun:21:00-sun:22:00"
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name}-db-final"

  tags = {
    Name = "${var.name}-db"
  }
}
