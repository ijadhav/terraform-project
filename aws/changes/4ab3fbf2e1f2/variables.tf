variable "name" {
  description = "Resource name identifier"
  type        = string
}

variable "aws_region" {
  description = "AWS region to launch resources in."
  type        = string
  default     = "us-east-1"
}

variable "ssh_key_name" {
  description = "SSH key for EC2 login"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "subnet_id" {
  description = "VPC Subnet ID for the instance"
  type        = string
}

variable "environment" {
  description = "Environment tag, e.g. dev, staging, prod."
  type        = string
}

variable "additional_tags" {
  description = "Map of additional tags to apply."
  type        = map(string)
  default     = {}
}
