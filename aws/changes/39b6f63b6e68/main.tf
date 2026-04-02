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

variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "example-ec2-instance"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH to the instance"
  type        = string
  default     = "0.0.0.0/0"
}

variable "public_key_path" {
  description = "Path to the public key to use for the EC2 key pair"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

locals {
  common_tags = {
    Project     = "example-ec2"
    Environment = "dev"
    ManagedBy   = "terraform"
  }

  nginx_user_data = <<-EOF
              #!/bin/bash
              set -euo pipefail

              # Update packages
              dnf update -y

              # Install nginx
              dnf install -y nginx

              # Enable and start nginx
              systemctl enable nginx
              systemctl start nginx

              # Simple index page
              echo "<h1>Welcome from nginx on Amazon Linux 2023</h1>" > /usr/share/nginx/html/index.html
          EOF
}

resource "tls_private_key" "this" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "this" {
  key_name   = "example-ec2-key"
  public_key = fileexists(var.public_key_path) ? file(var.public_key_path) : tls_private_key.this.public_key_openssh

  tags = merge(local.common_tags, {
    Name = "example-ec2-key"
  })
}

resource "aws_security_group" "ec2_sg" {
  name        = "example-ec2-sg"
  description = "Security group for example EC2 instance"

  ingress {
    description = "SSH from allowed CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "HTTP from anywhere for nginx"
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
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.common_tags, {
    Name = "example-ec2-sg"
  })
}

resource "aws_instance" "this" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.this.key_name
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]

  user_data = local.nginx_user_data

  tags = merge(local.common_tags, {
    Name = var.instance_name
  })
}

data "aws_ami" "amazon_linux" {
  most_recent = true

  owners = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.this.id
}

output "instance_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.this.public_ip
}

output "generated_private_key_pem" {
  description = "Generated private key in PEM format (if no public_key_path file exists). Handle securely."
  value       = fileexists(var.public_key_path) ? null : tls_private_key.this.private_key_pem
  sensitive   = true
}
