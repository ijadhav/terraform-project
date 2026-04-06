variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "instance_ami" {
  description = "AMI ID to use for the EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Subnet ID where the EC2 instance will be placed"
  type        = string
}

variable "security_group_ids" {
  description = "List of existing security group IDs to associate with the EC2 instance"
  type        = list(string)
  default     = []
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "example-ec2-instance"
}

variable "vpc_id" {
  description = "VPC ID where the HTTP security group will be created"
  type        = string
}
