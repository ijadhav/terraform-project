variable "aws_region" {
  description = "AWS region in which to create resources"
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the S3 bucket to create. Must be globally unique."
  type        = string
}

variable "environment" {
  description = "Environment tag for created resources"
  type        = string
  default     = "dev"
}

variable "enable_versioning" {
  description = "Whether to enable versioning on the S3 bucket"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}

# New variables for VPC, subnet, and EC2 instance

variable "vpc_cidr" {
  description = "CIDR block for the custom VPC named test"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for the custom subnet named test"
  type        = string
  default     = "10.0.1.0/24"
}

variable "availability_zone" {
  description = "Availability zone for the subnet (must belong to aws_region)"
  type        = string
  default     = "us-east-1a"
}

variable "ami_id" {
  description = "AMI ID for the Ishika EC2 instance (e.g., Amazon Linux 2 or Ubuntu)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for Ishika"
  type        = string
  default     = "t3.micro"
}
