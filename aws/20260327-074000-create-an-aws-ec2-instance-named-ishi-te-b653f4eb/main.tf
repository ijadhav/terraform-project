terraform {
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

variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

# Latest Amazon Linux 2 AMI in the selected region
data "aws_ami" "amazon_linux_2" {
  most_recent = true

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["amazon"]
}

# VPC and networking for public subnet
resource "aws_vpc" "ishi_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "ishi-vpc"
  }
}

resource "aws_internet_gateway" "ishi_igw" {
  vpc_id = aws_vpc.ishi_vpc.id

  tags = {
    Name = "ishi-igw"
  }
}

resource "aws_subnet" "ishi_public_subnet" {
  vpc_id                  = aws_vpc.ishi_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "ishi-public-subnet"
  }
}

resource "aws_route_table" "ishi_public_rt" {
  vpc_id = aws_vpc.ishi_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ishi_igw.id
  }

  tags = {
    Name = "ishi-public-rt"
  }
}

resource "aws_route_table_association" "ishi_public_rta" {
  subnet_id      = aws_subnet.ishi_public_subnet.id
  route_table_id = aws_route_table.ishi_public_rt.id
}

# Original security group kept for SSH, HTTP
resource "aws_security_group" "ishi_test_sg" {
  name        = "ishi-test-sg"
  description = "Security group for ishi-test EC2 instance"
  vpc_id      = aws_vpc.ishi_vpc.id

  ingress {
    description = "Allow HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Allow SSH from anywhere (adjust in production)"
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

  tags = {
    Name = "ishi-test-sg"
  }
}

# Custom security group with inbound HTTP 80
resource "aws_security_group" "ishi_http_only_sg" {
  name        = "ishi-http-only-sg"
  description = "Custom security group allowing only HTTP 80 inbound"
  vpc_id      = aws_vpc.ishi_vpc.id

  ingress {
    description = "Allow HTTP from anywhere"
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
    Name = "ishi-http-only-sg"
  }
}

resource "aws_instance" "ishi_test" {
  ami           = data.aws_ami.amazon_linux_2.id
  instance_type = "t3.micro"

  subnet_id              = aws_subnet.ishi_public_subnet.id
  vpc_security_group_ids = [
    aws_security_group.ishi_test_sg.id,
    aws_security_group.ishi_http_only_sg.id
  ]

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              amazon-linux-extras install nginx1 -y || yum install -y nginx
              systemctl enable nginx
              systemctl start nginx
              EOF

  tags = {
    Name = "ishi-test"
  }
}
