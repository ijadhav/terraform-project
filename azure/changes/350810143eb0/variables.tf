variable "location" {
  description = "Azure region for the MongoDB VM deployment"
  type        = string
  default     = "eastus"
}

variable "vm_size" {
  description = "Size of the MongoDB VM"
  type        = string
  default     = "Standard_B2ms"
}

variable "admin_username" {
  description = "Admin username for the MongoDB VM"
  type        = string
  default     = "azureuser"
}

variable "admin_ssh_public_key" {
  description = "SSH public key for admin user (e.g. contents of id_rsa.pub)"
  type        = string
}
