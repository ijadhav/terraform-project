variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for the EC2 instance (must belong to VPC ij-test)"
  type        = string
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name for the EC2 key pair"
  type        = string
}

variable "public_key" {
  description = "Public SSH key material for the key pair"
  type        = string
}
