variable "location" {
  description = "Azure region to deploy resources into"
  type        = string
  default     = "eastus"
}

variable "vm_size" {
  description = "Size of the Azure VM for MongoDB and Nginx"
  type        = string
  default     = "Standard_B2ms"
}

variable "admin_username" {
  description = "Admin username for the Linux VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "SSH public key for admin user"
  type        = string
}
