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

  tags = {
    Name = "example-ec2-instance"
  }
}
