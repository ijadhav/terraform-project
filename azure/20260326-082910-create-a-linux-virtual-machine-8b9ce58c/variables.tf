variable "resource_group_name" {
  description = "The name of the resource group."
  type        = string
  default     = "example-resources"
}

variable "location" {
  description = "The location where resources will be created."
  type        = string
  default     = "East US"
}

variable "vm_size" {
  description = "The size of the virtual machine."
  type        = string
  default     = "Standard_B1ls"
}

variable "admin_username" {
  description = "Admin username for the Linux VM."
  type        = string
  default     = "azureuser"
}

variable "admin_password" {
  description = "Admin password for the Linux VM."
  type        = string
}
