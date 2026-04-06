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

# NOTE: Azure storage account names must be globally unique, 3-24 chars, lowercase letters and numbers only.
# "test" is valid syntactically but may conflict if already taken in the target subscription/tenant.
variable "storage_account_name" {
  description = "Globally unique name for the storage account (3-24 lowercase letters and numbers)"
  type        = string
  default     = "test"
}

# NOTE: Cosmos DB account names must be globally unique, 3-44 chars, lowercase letters and numbers only.
# "test" is valid syntactically but may conflict if already taken.
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
