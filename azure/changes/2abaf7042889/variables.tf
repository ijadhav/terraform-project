variable "location" {
  description = "Azure region where resources will be created"
  type        = string
  default     = "eastus"
}

variable "admin_username" {
  description = "Admin username for the Linux VM"
  type        = string
  default     = "azureuser"
}

variable "admin_ssh_public_key" {
  description = "SSH public key for the Linux VM admin user"
  type        = string
}
