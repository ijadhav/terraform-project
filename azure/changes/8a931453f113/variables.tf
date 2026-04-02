variable "prefix" {
  description = "Prefix used for naming Azure resources."
  type        = string
  default     = "oracle-demo"
}

variable "location" {
  description = "Azure region where resources will be deployed."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group to create for Oracle VM."
  type        = string
  default     = "rg-oracle-demo"
}

variable "vm_size" {
  description = "Size of the Azure VM for Oracle. Choose according to Oracle sizing guidance."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "admin_username" {
  description = "Admin username for the Oracle VM."
  type        = string
  default     = "oracleadmin"
}

variable "ssh_public_key" {
  description = "SSH public key for VM admin access."
  type        = string
}

variable "oracle_data_disk_size_gb" {
  description = "Size of the managed disk (in GB) for Oracle data."
  type        = number
  default     = 256
}
