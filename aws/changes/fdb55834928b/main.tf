terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

module "ec2" {
  source = "../../modules/ec2"

  name     = "test"
  ssh_key  = var.ssh_key
  user_tag = var.user_tag
  tags     = var.tags
}

module "s3" {
  source = "../../modules/s3"

  name      = "s3"
  aws_region = var.aws_region
  user_tag  = var.user_tag
  tags      = var.tags
}
