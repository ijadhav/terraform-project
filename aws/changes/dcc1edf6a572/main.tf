terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "example-vpc"
  }
}

# Public subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "example-public-subnet"
  }
}

# Internet gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "example-igw"
  }
}

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "example-public-rt"
  }
}

# Associate route table with public subnet
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Security group allowing SSH and HTTP for nginx
resource "aws_security_group" "ssh" {
  name        = "example-ec2-ssh"
  description = "Allow SSH and HTTP inbound traffic"
  vpc_id      = aws_vpc.main.id

  ingress {
    description      = "SSH from anywhere"
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTP for nginx"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "example-ec2-ssh"
  }
}

# Key pair (expects an existing local public key file)
variable "public_key_path" {
  description = "Path to your SSH public key file"
  type        = string
}

resource "aws_key_pair" "default" {
  key_name   = "example-ec2-key"
  public_key = file(var.public_key_path)
}

# EC2 instance with user data to install nginx
resource "aws_instance" "example" {
  ami                    = "ami-0fc5d935ebf8bc3bc" # Ubuntu 22.04 LTS in us-east-1 (update as needed)
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ssh.id]
  key_name               = aws_key_pair.default.key_name

  associate_public_ip_address = true

  user_data = <<-EOF
              #!/bin/bash
              set -xe

              # Update package index
              apt-get update -y

              # Install nginx
              apt-get install -y nginx

              # Enable and start nginx
              systemctl enable nginx
              systemctl start nginx

              # Simple index page
              echo "<h1>nginx installed via Terraform user_data</h1>" > /var/www/html/index.nginx-debian.html
              EOF

  tags = {
    Name = "example-ec2-instance"
  }
}

output "instance_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.example.public_ip
}
