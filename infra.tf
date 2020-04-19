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
# Console, (and could perhaps be used to replace some of the use of the AWS CLI
# in `manage.py`, as desired/useful).
#
# NOTE: But, database could also, alternatively, be managed as part of Elastic
# Beanstalk (saved) configuration....
#

#
# BEGIN: terraform set-up
#

terraform {
  required_version = "~> 0.12.6"
}

provider "aws" {
  version    = "~> 2.22"
  region     = "us-west-2"
}

#
# END: terraform set-up
#

#
# BEGIN: database
#

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

#
# END: database
#

#
# BEGIN: background jobs
#

# NOTE: there are a number of alternatives to this set-up:
#
# 1. since we currently have an Elastic Beanstalk environment, jobs *could* be
#    run from here
#
# 2. if we were instead already using ECS, a scheduled job could be run in our
#    (existing) cluster
#
# 3. since we don't have a running cluster, rather than maintain one just for a
#    periodic job, we could use the ECS Fargate environment, (tho it might be
#    expensive)
#
# Moreover, AWS has recently added the ability to scale up an ECS cluster from
# zero, (and ostensibly to scale it back down) -- at which point ECS and Batch
# offer very similar features, at least for simpler use-cases.
#
# What we'll try however is AWS Batch, and using spot instances. This set-up
# should both be intended for our use-case and the most cost-effective.

# Batch compute environment #

resource "aws_iam_role" "appy_ecs_instance_role" {
  name = "appy-ecs-instance-role"

  assume_role_policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
    {
        "Action": "sts:AssumeRole",
        "Effect": "Allow",
        "Principal": {
        "Service": "ec2.amazonaws.com"
        }
    }
    ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "appy_ecs_instance_role" {
  role       = aws_iam_role.appy_ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "appy_ecs_instance_profile" {
  name = "appy-ecs-instance-profile"
  role = aws_iam_role.appy_ecs_instance_role.name
}

# resource "aws_iam_role" "appy_batch_service_role" {
#   name = "appy-batch-service-role"

#   assume_role_policy = <<EOF
# {
#     "Version": "2012-10-17",
#     "Statement": [
#     {
#         "Action": "sts:AssumeRole",
#         "Effect": "Allow",
#         "Principal": {
#         "Service": "batch.amazonaws.com"
#         }
#     }
#     ]
# }
# EOF
# }

# resource "aws_iam_role_policy_attachment" "appy_batch_service_role" {
#   role       = aws_iam_role.appy_batch_service_role.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
# }

resource "aws_batch_compute_environment" "appy_web_default" {
  compute_environment_name = "appy-web-default"

  compute_resources {
    instance_role = aws_iam_instance_profile.appy_ecs_instance_profile.arn

    instance_type = [
      "m3",
      "m5",
    ]

    max_vcpus = 2  # in fact we're likely single-threaded
    min_vcpus = 0

    security_group_ids = [
      "dsapp-sg-general",
    ]

    subnets = [
      "subnet-495b603f",
    ]

    ec2_key_pair = "appy-reviews"

    type = "SPOT"
    bid_percentage = 100
    spot_iam_fleet_role = "arn:aws:iam::093198349272:role/aws-service-role/spotfleet.amazonaws.com/AWSServiceRoleForEC2SpotFleet"
  }

  service_role = "arn:aws:iam::093198349272:role/service-role/AWSBatchServiceRole"
  # service_role = aws_iam_role.appy_ecs_instance_role.arn
  # depends_on   = [aws_iam_role_policy_attachment.appy_batch_service_role]
  type         = "MANAGED"
}

# Batch job queue #

resource "aws_batch_job_queue" "appy_web_default" {
  name                 = "appy-web-default"
  state                = "ENABLED"
  priority             = 1
  compute_environments = [aws_batch_compute_environment.appy_web_default.arn]
}

# Batch job definition #

variable "appy_image_uri" {
  type = string
}

resource "aws_batch_job_definition" "appy_web_default" {
  name = "appy-web-default"
  type = "container"

  retry_strategy {
    attempts = 2
  }

  container_properties = <<CONTAINER_PROPERTIES
{
  "image": "${var.appy_image_uri}:latest",
  "user": "webapp",
  "memory": 2000,
  "vcpus": 2
}
CONTAINER_PROPERTIES
  # "command": ["./manage.py", "loadwufoo", "--verbosity=2", "--stage=application", "-"],
  # "environment": [
  #   {
  #     "name": "string",
  #     "value": "string"
  #   }
  # ],
}

#
# END: background jobs
#
