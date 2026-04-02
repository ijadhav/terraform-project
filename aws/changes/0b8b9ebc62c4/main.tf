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
  region = var.aws_region
}

resource "aws_instance" "example" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  associate_public_ip_address = true

  user_data = <<-EOF
              #!/bin/bash
              set -e

              # Update packages
              yum update -y || apt-get update -y || true

              # Install nginx (Amazon Linux / RHEL / CentOS)
              if command -v yum >/dev/null 2>&1; then
                amazon-linux-extras install -y nginx1 || yum install -y nginx
              # Install nginx (Debian / Ubuntu)
              elif command -v apt-get >/dev/null 2>&1; then
                apt-get install -y nginx
              fi

              systemctl enable nginx || true
              systemctl start nginx || true

              # Simple index page
              echo "<h1>Nginx is running on $(hostname)</h1>" > /usr/share/nginx/html/index.html 2>/dev/null || \
              echo "<h1>Nginx is running on $(hostname)</h1>" > /var/www/html/index.nginx-debian.html 2>/dev/null || true
              EOF

  tags = {
    Name = "test"
  }
}
