provider "aws" {
  region = var.aws_region
}

resource "aws_security_group" "example_sg" {
  name        = "example-ec2-sg"
  description = "Security group for example EC2 instances"

  ingress {
    description = "Allow SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "example_1" {
  ami                    = var.instance_ami
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.example_sg.id]

  tags = {
    Name = "example-instance-1"
  }
}

resource "aws_instance" "example_2" {
  ami                    = var.instance_ami
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.example_sg.id]

  tags = {
    Name = "example-instance-2"
  }
}
