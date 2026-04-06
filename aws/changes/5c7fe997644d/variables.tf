variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "Instance type for the EC2 instance"
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Subnet ID where the EC2 instance will be deployed"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where security group will be created"
  type        = string
}

variable "key_name" {
  description = "Name for the EC2 key pair"
  type        = string
  default     = "ec2-key"
}

variable "public_key" {
  description = "Public SSH key to associate with the key pair"
  type        = string
}

variable "associate_public_ip" {
  description = "Whether to associate a public IP with the instance"
  type        = bool
  default     = true
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "example-ec2-instance"
}
