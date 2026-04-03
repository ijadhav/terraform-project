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

resource "aws_instance" "example" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  associate_public_ip_address = true

  tags = {
    Name = "test"
  }
}
