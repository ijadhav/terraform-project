variable "resource_group_name" {
  description = "Name of the resource group for MongoDB resources"
  type        = string
  default     = "mongodb-rg"
}

variable "location" {
  description = "Azure region for MongoDB resources"
  type        = string
  default     = "eastus"
}

variable "vm_size" {
  description = "Size of the MongoDB virtual machine"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Admin username for the MongoDB VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "SSH public key for VM admin user"
  type        = string
}

variable "storage_account_name" {
  description = "Name of the storage account for MongoDB-related data and backups"
  type        = string
}
