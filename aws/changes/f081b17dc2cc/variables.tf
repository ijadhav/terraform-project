variable "aws_region" {
  description = "AWS region for the resources."
  type        = string
}

variable "name" {
  description = "Name assigned to resources."
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources."
  type        = map(string)
}
