variable "location" {
  type        = string
  description = "Azure region for MongoDB storage resources"
  default     = "eastus"
}

variable "mongo_storage_account_name" {
  type        = string
  description = "Globally unique name for the MongoDB storage account"
}

variable "general_storage_account_name" {
  type        = string
  description = "Globally unique name for the general purpose storage account (S3-like)"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to storage resources"
  default = {
    environment = "dev"
    workload    = "storage"
  }
}
