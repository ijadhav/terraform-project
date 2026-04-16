variable "ami" {
  description = "The AMI ID for the Linux VM."
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "The type of instance to use for the Linux VM."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "The subnet ID for the instance."
  type        = string
  default     = ""
}

variable "vpc_security_group_ids" {
  description = "List of VPC security group IDs to assign."
  type        = list(string)
  default     = []
}

variable "key_name" {
  description = "Name of the SSH key pair to use."
  type        = string
  default     = ""
}

variable "tags" {
  description = "A map of tags to assign to the resource."
  type        = map(string)
  default     = {}
}
