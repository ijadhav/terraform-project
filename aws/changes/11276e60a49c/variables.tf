variable "aws_region" {
  description = "AWS region in which to create the S3 bucket"
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the S3 bucket to create. Must be globally unique."
  type        = string
}

variable "environment" {
  description = "Environment tag for the S3 bucket"
  type        = string
  default     = "dev"
}

variable "enable_versioning" {
  description = "Whether to enable versioning on the S3 bucket"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags to apply to the S3 bucket"
  type        = map(string)
  default     = {}
}
