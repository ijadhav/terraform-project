variable "location" {
  description = "Azure region where resources will be created"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-oracle-vm"
}

variable "name_prefix" {
  description = "Prefix used for naming Azure resources"
  type        = string
  default     = "oracle"
}

variable "vm_size" {
  description = "Size of the Oracle Linux virtual machine"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "admin_username" {
  description = "Admin username for the VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file to access the VM"
  type        = string
}
