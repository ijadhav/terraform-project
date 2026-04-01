variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "ec2_instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "sandbox-ec2"
}

variable "ec2_instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "ec2_module_source" {
  description = "Source for the EC2 module (Git URL, registry, or local path)"
  type        = string
  default     = "./modules/ec2-instance"
}
