variable "resource_group_name" {
  description = "Name of the resource group."
  type        = string
  default     = "example-resources"
}

variable "location" {
  description = "Azure location for resources."
  type        = string
  default     = "East US"
}

variable "vm_size" {
  description = "The size of the virtual machine."
  type        = string
  default     = "Standard_DS1_v2"
}

variable "admin_username" {
  description = "Admin username for the VM."
  type        = string
}

variable "admin_password" {
  description = "Admin password for the VM."
  type        = string
}
