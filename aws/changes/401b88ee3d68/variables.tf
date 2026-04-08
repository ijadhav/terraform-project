variable "region" {
  description = "AWS region for the instance."
  type        = string
}

variable "ec2_name" {
  description = "Name tag for the EC2 instance."
  type        = string
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Subnet ID for the EC2 instance."
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs to associate."
  type        = list(string)
}

variable "default_tags" {
  description = "Default tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "bucket_name" {
  description = "Name of the S3 bucket."
  type        = string
}

variable "s3_versioning" {
  description = "Enable versioning for the S3 bucket."
  type        = bool
  default     = false
}

variable "s3_acl" {
  description = "Canned ACL for the S3 bucket."
  type        = string
  default     = "private"
}
