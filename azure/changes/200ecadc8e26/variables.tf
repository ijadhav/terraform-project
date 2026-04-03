variable "resource_group_name" {
  description = "Name of the resource group to create/use for the VM"
  type        = string
  default     = "rg-vm-demo"
}

variable "location" {
  description = "Azure region where the VM will be created"
  type        = string
  default     = "eastus"
}

variable "vm_name" {
  description = "Name of the virtual machine"
  type        = string
  default     = "demo-vm"
}

variable "vm_size" {
  description = "Size/sku of the virtual machine"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Admin username for the virtual machine"
  type        = string
  default     = "azureuser"
}
