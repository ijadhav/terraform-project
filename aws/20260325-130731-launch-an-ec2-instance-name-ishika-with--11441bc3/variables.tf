variable "aws_region" {
  description = "AWS region for resources."
  type        = string
  default     = "us-east-1"
}

variable "windows_ami" {
  description = "Windows AMI ID."
  type        = string
}

variable "vpc_name" {
  description = "Name of the custom VPC."
  type        = string
  default     = "ij-test"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}
