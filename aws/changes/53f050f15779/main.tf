terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_security_group" "test_http" {
  name        = "test-ec2-http-sg"
  description = "Security group for test EC2 instance allowing HTTP"

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    {
      Name = "test-ec2-http-sg"
    },
    var.default_tags,
  )
}

resource "aws_instance" "test" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  associate_public_ip_address = true

  vpc_security_group_ids = [aws_security_group.test_http.id]

  tags = merge(
    {
      Name = "test-ec2-instance"
    },
    var.default_tags,
  )
}
