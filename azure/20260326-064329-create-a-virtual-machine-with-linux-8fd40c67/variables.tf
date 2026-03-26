variable "resource_group_name" {
  description = "The name of the resource group."
  type        = string
}

variable "location" {
  description = "The Azure location for resources."
  default     = "East US"
}

variable "vm_size" {
  description = "The size of the virtual machine."
  default     = "Standard_B1s"
}

variable "admin_username" {
  description = "The admin username for the VM."
  type        = string
}

variable "admin_password" {
  description = "The password for the admin user."
  type        = string
  sensitive   = true
}
