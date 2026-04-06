terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# General variables
variable "location" {
  description = "Azure region for the storage account"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group for MongoDB storage"
  type        = string
  default     = "rg-mongodb-storage"
}

variable "storage_account_name" {
  description = "Globally unique name for the storage account used with MongoDB"
  type        = string
  default     = "stmongodbstorage001"
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    environment = "dev"
    workload    = "mongodb"
  }
}

# Resource group for MongoDB storage
resource "azurerm_resource_group" "mongodb_rg" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# Storage account intended for MongoDB-related data (e.g., backups, exports)
resource "azurerm_storage_account" "mongodb_storage" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.mongodb_rg.name
  location                 = azurerm_resource_group.mongodb_rg.location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  account_kind             = "StorageV2"

  enable_https_traffic_only = true

  min_tls_version = "TLS1_2"

  allow_blob_public_access = false

  tags = merge(var.tags, {
    data_type = "mongodb"
  })
}

# Blob container to hold MongoDB data (e.g., backups)
resource "azurerm_storage_container" "mongodb_backups" {
  name                  = "mongodb-backups"
  storage_account_name  = azurerm_storage_account.mongodb_storage.name
  container_access_type = "private"
}

output "mongodb_storage_account_id" {
  description = "ID of the MongoDB storage account"
  value       = azurerm_storage_account.mongodb_storage.id
}

output "mongodb_backup_container_name" {
  description = "Name of the MongoDB backup container"
  value       = azurerm_storage_container.mongodb_backups.name
}
