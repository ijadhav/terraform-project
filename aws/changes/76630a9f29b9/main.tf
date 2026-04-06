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

# Security group allowing HTTP (80) from anywhere
resource "aws_security_group" "http_80" {
  name        = "example-http-80-sg"
  description = "Allow HTTP inbound traffic on port 80"
  vpc_id      = var.vpc_id

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

  tags = {
    Name = "example-http-80-sg"
  }
}

resource "aws_instance" "example" {
  ami           = var.instance_ami
  instance_type = var.instance_type
  subnet_id     = var.subnet_id

  # Attach existing security groups (if any) plus the new HTTP SG
  vpc_security_group_ids = concat(var.security_group_ids, [aws_security_group.http_80.id])

  tags = {
    Name = var.instance_name
  }
}
