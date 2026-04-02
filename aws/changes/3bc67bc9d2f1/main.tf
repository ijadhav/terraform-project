terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "example" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.security_group_ids

  user_data = <<-EOF
              #!/bin/bash
              set -euo pipefail

              # Update packages and install nginx (Amazon Linux / RHEL based)
              if command -v yum >/dev/null 2>&1; then
                yum update -y
                yum install -y nginx
              elif command -v apt-get >/dev/null 2>&1; then
                apt-get update -y
                apt-get install -y nginx
              fi

              systemctl enable nginx || true
              systemctl start nginx || true
              EOF

  tags = merge(var.tags, {
    Name = "example-ec2-instance"
  })
}
