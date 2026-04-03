variable "location" {
  description = "Azure region where the VM will be deployed"
  type        = string
  default     = "canadacentral"
}

variable "environment" {
  description = "Environment name (e.g., dev, sbx, prod)"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to create/use for the VM"
  type        = string
}

variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = string
  default     = "10.10.0.0/16"
}

variable "subnet_address_prefix" {
  description = "Address prefix for the VM subnet"
  type        = string
  default     = "10.10.1.0/24"
}

variable "ssh_source_cidr" {
  description = "CIDR block allowed to SSH into the VM"
  type        = string
  default     = "0.0.0.0/0"
}

variable "enable_public_ip" {
  description = "Whether to create a public IP for the VM"
  type        = bool
  default     = true
}

variable "linux_distribution_name" {
  description = "Linux distribution image name supported by the internal VM module (e.g., ubuntu2004, ubuntu2204)"
  type        = string
  default     = "ubuntu2204"
}

variable "vm_size" {
  description = "Size of the Azure VM"
  type        = string
  default     = "Standard_B2s"
}

variable "generate_admin_ssh_key" {
  description = "Whether the module should generate an SSH key for the admin user"
  type        = bool
  default     = false
}

variable "admin_ssh_key_data" {
  description = "Existing public SSH key to use when generate_admin_ssh_key is false"
  type        = string
  default     = ""
}

variable "additional_data_disks" {
  description = "List of data disk sizes in GB to attach to the VM"
  type        = list(number)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    ProjectName = "vm"
    Env         = "sbx"
    Owner       = "STO"
    repo        = "tf-azure-vm"
  }
}
