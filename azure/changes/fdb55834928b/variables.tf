variable "name" {
  type        = string
  description = "Resource name and Name tag."
}

variable "resource_group_name" {
  type        = string
  description = "Azure resource group name."
}

variable "location" {
  type        = string
  description = "Azure location for all resources."
}

variable "tags" {
  type        = map(string)
  description = "Resource tags."
  default     = {}
}
