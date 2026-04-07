variable "aws_region" {
  type        = string
  description = "AWS region to launch resources."
}

variable "name" {
  type        = string
  description = "Resource name and name tag."
}

variable "ssh_key" {
  type        = string
  description = "SSH key name to use for EC2-related resources."
}

variable "user_tag" {
  type        = string
  description = "Value to use for auditing tag 'user:tag'"
}

variable "tags" {
  type        = map(string)
  description = "Additional resource tags."
  default     = {}
}
