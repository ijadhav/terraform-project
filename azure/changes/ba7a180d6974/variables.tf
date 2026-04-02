variable "location" {
  description = "Azure region where resources will be created"
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-oracle-vm"
}

variable "name_prefix" {
  description = "Prefix used for all resource names"
  type        = string
  default     = "oracle"
}

variable "vm_size" {
  description = "Size of the Azure VM suitable for Oracle workloads"
  type        = string
  default     = "Standard_D4s_v5"
}

variable "os_disk_size_gb" {
  description = "OS disk size in GB for the VM"
  type        = number
  default     = 128
}

variable "admin_username" {
  description = "Admin username for the Linux VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file used for VM authentication"
  type        = string
}

# Default to an Oracle-compatible Oracle Linux image from Azure Marketplace.
# Validate in your subscription/region and adjust if needed.
variable "image_publisher" {
  description = "Image publisher for the Linux VM (e.g., Oracle Linux)"
  type        = string
  default     = "Oracle"
}

variable "image_offer" {
  description = "Image offer for the Linux VM"
  type        = string
  default     = "Oracle-Linux"
}

variable "image_sku" {
  description = "Image SKU for the Linux VM"
  type        = string
  default     = "ol87-gen2"
}

variable "image_version" {
  description = "Image version for the Linux VM"
  type        = string
  default     = "latest"
}

variable "environment" {
  description = "Environment tag (e.g., dev, test, prod)"
  type        = string
  default     = "dev"
}
