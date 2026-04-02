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

resource "aws_instance" "example" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t2.nano"

  root_block_device {
    volume_size = 24
    volume_type = "gp3"
  }

  tags = {
    Name = "example-t2-nano"
  }
}
