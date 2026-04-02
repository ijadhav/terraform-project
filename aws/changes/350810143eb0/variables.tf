variable "aws_region" {
  description = "AWS region for the EC2 instance"
  type        = string
  default     = "us-east-2"
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance in us-east-2 (e.g., latest Amazon Linux 2)"
  type        = string
}

variable "key_name" {
  description = "Name of the existing EC2 Key Pair to enable SSH access"
  type        = string
}
