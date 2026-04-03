variable "location" {
  description = "Azure region for the VM."
  type        = string
}

variable "resource_group_name" {
  description = "Name of the existing resource group in which to create the VM."
  type        = string
}

variable "subscription_type" {
  description = "Subscription type short code (e.g. sbx, dev, prod) to follow Vena naming standards."
  type        = string
}

variable "env" {
  description = "Environment name (e.g. sbx, dev, qa, prod)."
  type        = string
}

variable "project_name" {
  description = "Project name tag value."
  type        = string
}

variable "owner" {
  description = "Owner tag value (team or person)."
  type        = string
}

variable "repo" {
  description = "Repository name tag value."
  type        = string
}

variable "additional_tags" {
  description = "Additional tags to merge with standard tags."
  type        = map(string)
  default     = {}
}

variable "subnet_id" {
  description = "ID of an existing subnet where the VM NIC will be placed."
  type        = string
}

variable "enable_public_ip" {
  description = "Whether to create and associate a public IP with the VM."
  type        = bool
  default     = false
}

variable "ssh_source_address_prefix" {
  description = "CIDR or source prefix allowed to SSH to the VM (e.g. office IP range)."
  type        = string
  default     = "0.0.0.0/0"
}

variable "vm_size" {
  description = "Azure VM size for the Linux VM."
  type        = string
  default     = "Standard_B2ms"
}

variable "os_disk_storage_account_type" {
  description = "OS disk storage account type."
  type        = string
  default     = "Premium_LRS"
}

variable "os_disk_size_gb" {
  description = "OS disk size in GB."
  type        = number
  default     = 64
}

variable "admin_ssh_public_key" {
  description = "SSH public key for the admin user."
  type        = string
}

variable "image_publisher" {
  description = "Publisher for the Linux image."
  type        = string
  default     = "Canonical"
}

variable "image_offer" {
  description = "Offer for the Linux image."
  type        = string
  default     = "0001-com-ubuntu-server-focal"
}

variable "image_sku" {
  description = "SKU for the Linux image."
  type        = string
  default     = "20_04-lts"
}

variable "image_version" {
  description = "Version for the Linux image. Use 'latest' to always get the latest."
  type        = string
  default     = "latest"
}
