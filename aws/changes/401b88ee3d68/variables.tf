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
