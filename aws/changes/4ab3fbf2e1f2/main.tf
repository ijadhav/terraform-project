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

  name            = var.name
  ssh_key_name    = var.ssh_key_name
  instance_type   = var.instance_type
  subnet_id       = var.subnet_id
  region          = var.aws_region
  environment     = var.environment
  additional_tags = var.additional_tags

  tags = merge({
    Name        = var.name
    Environment = var.environment
    ChangeType  = "ec2"
  }, var.additional_tags)
)
