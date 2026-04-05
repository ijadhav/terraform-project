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

# Existing S3 bucket resources
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  tags = merge(
    {
      Name        = var.bucket_name
      Environment = var.environment
    },
    var.tags,
  )
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "s3_bucket_name" {
  description = "Name of the created S3 bucket"
  value       = aws_s3_bucket.this.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the created S3 bucket"
  value       = aws_s3_bucket.this.arn
}

# New networking and EC2 resources

# Custom VPC named "test"
resource "aws_vpc" "test" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(
    {
      Name = "test"
    },
    var.tags,
  )
}

# Internet Gateway for public access
resource "aws_internet_gateway" "test" {
  vpc_id = aws_vpc.test.id

  tags = merge(
    {
      Name = "test-igw"
    },
    var.tags,
  )
}

# Custom public subnet named "test"
resource "aws_subnet" "test" {
  vpc_id                  = aws_vpc.test.id
  cidr_block              = var.subnet_cidr
  map_public_ip_on_launch = true
  availability_zone       = var.availability_zone

  tags = merge(
    {
      Name = "test"
    },
    var.tags,
  )
}

# Public route table
resource "aws_route_table" "test_public" {
  vpc_id = aws_vpc.test.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.test.id
  }

  tags = merge(
    {
      Name = "test-public-rt"
    },
    var.tags,
  )
}

# Associate subnet with public route table
resource "aws_route_table_association" "test_public_assoc" {
  subnet_id      = aws_subnet.test.id
  route_table_id = aws_route_table.test_public.id
}

# Security group to allow HTTP and SSH
resource "aws_security_group" "ishika_sg" {
  name        = "ishika-sg"
  description = "Security group for Ishika EC2 instance"
  vpc_id      = aws_vpc.test.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH from anywhere"
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

  tags = merge(
    {
      Name = "ishika-sg"
    },
    var.tags,
  )
}

# EC2 instance "Ishika" with nginx installed and custom welcome page
resource "aws_instance" "ishika" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.test.id
  vpc_security_group_ids = [aws_security_group.ishika_sg.id]
  associate_public_ip_address = true

  user_data = <<-EOF
              #!/bin/bash
              yum update -y || apt-get update -y

              # Install nginx (handle both Amazon Linux/Yum and Ubuntu/Apt)
              if command -v yum >/dev/null 2>&1; then
                amazon-linux-extras install -y nginx1 || yum install -y nginx
                systemctl enable nginx
                systemctl start nginx
              else
                apt-get install -y nginx
                systemctl enable nginx
                systemctl start nginx
              fi

              echo "hello welcome to nginx" > /usr/share/nginx/html/index.html 2>/dev/null || \
              echo "hello welcome to nginx" > /var/www/html/index.nginx-debian.html
              EOF

  tags = merge(
    {
      Name = "Ishika"
    },
    var.tags,
  )
}

output "ishika_public_ip" {
  description = "Public IP address of the Ishika EC2 instance"
  value       = aws_instance.ishika.public_ip
}

output "ishika_public_dns" {
  description = "Public DNS name of the Ishika EC2 instance"
  value       = aws_instance.ishika.public_dns
}
