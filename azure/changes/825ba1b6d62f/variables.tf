variable "project_name" {
  description = "Short project name used for resource naming."
  type        = string
  default     = "demo"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group to create."
  type        = string
  default     = "rg-demo-vm"
}

variable "vm_size" {
  description = "Size/SKU of the virtual machine."
  type        = string
  default     = "Standard_B2ms"
}

variable "admin_username" {
  description = "Admin username for the VM."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file used for VM admin login."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}
