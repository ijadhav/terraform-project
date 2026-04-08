terraform {
  required_version = ">= 1.0.0"
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

module "s3_storage" {
  source = "../../modules/s3_storage"

  bucket_name = var.bucket_name
  environment = var.environment
  tags        = var.tags
}
