variable "resource_group_name" {
  description = "Name of the resource group to create"
  type        = string
  default     = "rg-linux-vm-example"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "prefix" {
  description = "Prefix used for all resource names"
  type        = string
  default     = "linuxvm"
}

variable "vm_size" {
  description = "Size of the Linux VM"
  type        = string
  default     = "Standard_B1s"
}

variable "admin_username" {
  description = "Admin username for the Linux VM"
  type        = string
  default     = "azureuser"
}

variable "admin_ssh_public_key" {
  description = "SSH public key for admin user"
  type        = string
}

variable "image_publisher" {
  description = "Publisher of the Linux image"
  type        = string
  default     = "Canonical"
}

variable "image_offer" {
  description = "Offer of the Linux image"
  type        = string
  default     = "0001-com-ubuntu-server-focal"
}

variable "image_sku" {
  description = "SKU of the Linux image"
  type        = string
  default     = "20_04-lts"
}

variable "image_version" {
  description = "Version of the Linux image"
  type        = string
  default     = "latest"
}
