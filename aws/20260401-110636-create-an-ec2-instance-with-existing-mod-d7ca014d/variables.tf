variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "ec2_instance_name" {
  description = "Name tag for the EC2 instance with NGINX"
  type        = string
  default     = "sandbox-ec2-nginx"
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

variable "ec2_user_data" {
  description = "User data script to run on EC2 instance bootstrap (for NGINX instance)"
  type        = string
  default     = "#!/bin/bash\n\nyum update -y || apt-get update -y\n\n# Install nginx for Amazon Linux / RHEL-based\nyum install -y nginx || apt-get install -y nginx\n\n# Enable and start nginx\nsystemctl enable nginx || true\nsystemctl start nginx || service nginx start\n"
}

variable "ec2_basic_instance_name" {
  description = "Name tag for the basic EC2 instance without extras"
  type        = string
  default     = "sandbox-ec2-basic"
}

variable "ec2_basic_instance_type" {
  description = "EC2 instance type for the basic instance"
  type        = string
  default     = "t3.micro"
}
