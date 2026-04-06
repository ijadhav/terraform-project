variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-mongo-storage"
}

# Azure StorageV2 account used as S3-equivalent object storage
variable "storage_account_name" {
  description = "Globally unique name for the storage account (3-24 lowercase letters and numbers)"
  type        = string
  default     = "test"
}

variable "cosmos_account_name" {
  description = "Name for the Cosmos DB account (must be globally unique, 3-44 lowercase letters and numbers)"
  type        = string
  default     = "test"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    environment = "dev"
    project     = "mongodb-storage"
  }
}
