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

resource "aws_instance" "test" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  associate_public_ip_address = true

  tags = merge(
    {
      Name = "test-ec2-instance"
    },
    var.default_tags,
  )
}

resource "aws_s3_bucket" "test" {
  bucket = var.s3_bucket_name

  tags = merge(
    {
      Name = "test-s3-bucket"
    },
    var.default_tags,
  )
}

resource "aws_s3_bucket_public_access_block" "test" {
  bucket = aws_s3_bucket.test.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
