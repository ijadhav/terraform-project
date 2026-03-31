terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# NOTE: Replace the ami value with a valid AMI ID for your region.
resource "aws_instance" "example" {
  ami           = "ami-0123456789abcdef0"
  instance_type = "t3.micro"

  user_data = <<-EOF
              #!/bin/bash
              yum update -y || apt-get update -y
              # Try installing nginx with yum (Amazon Linux/RHEL/CentOS) then fallback to apt (Ubuntu/Debian)
              yum install -y nginx || apt-get install -y nginx
              systemctl enable nginx || update-rc.d nginx defaults
              systemctl start nginx || service nginx start
              EOF

  tags = {
    Name = "example-ec2-instance"
  }
}
