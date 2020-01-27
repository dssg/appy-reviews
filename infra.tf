# configuration of basic infrastructure
#
#
# appy is currently an Elastic Beanstalk-deployed Docker app, dependent upon a
# separate RDS instance.
#
# management of the project is principally performed via `manage` commands;
# (and, for consistency, a `manage stack` command covers this).
#
# terraform is here in use to replace manual configuration performed via the AWS
# Console, (and could perhaps be used to replace use of AWS CLI in `manage.py`,
# as desired/useful).
#
# NOTE: But, database could also, alternatively, be managed as part of Elastic
# Beanstalk (saved) configuration....
#

terraform {
  required_version = "~> 0.12.6"
}

provider "aws" {
  version    = "~> 2.22"
  region     = "us-west-2"
}

variable "appy_db_snapshot_id" {
  type = string
}

resource "aws_db_instance" "default" {
  identifier           = "appy"
  instance_class       = "db.t2.medium"
  parameter_group_name = "default.postgres10"
  storage_encrypted    = true
  iam_database_authentication_enabled = true
  tags = {
    workload-type      = "production"
  }

  # specified by env or shell input prompt
  #
  # snapshot from which to relaunch for the year
  snapshot_identifier  = var.appy_db_snapshot_id

  # provisioned elsewhere
  #
  # db-dedicated subnet group in same vpc as beanstalk env
  db_subnet_group_name = "dsapp-db-subnet-group"
}
