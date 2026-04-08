terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

module "ec2_instance" {
  source = "../../modules/aws-ec2-instance"

  name          = var.ec2_name
  ami_id        = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.subnet_id
  vpc_security_group_ids = var.security_group_ids

  tags = merge(var.default_tags, {
    Name = var.ec2_name
  })
}
