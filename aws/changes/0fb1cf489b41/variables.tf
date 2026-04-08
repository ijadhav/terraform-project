variable "aws_region" {
  description = "AWS region to launch resources in"
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "environment" {
  description = "Environment tag, e.g. dev, staging, prod"
  type        = string
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}
