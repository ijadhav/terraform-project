terraform {
  required_version = ">= 1.3.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "mongo_rg" {
  name     = "rg-mongo-storage"
  location = var.location
}

resource "azurerm_storage_account" "mongo_storage" {
  name                     = var.mongo_storage_account_name
  resource_group_name      = azurerm_resource_group.mongo_rg.name
  location                 = azurerm_resource_group.mongo_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  enable_https_traffic_only = true

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "mongo_backups" {
  name                  = "mongo-backups"
  storage_account_name  = azurerm_storage_account.mongo_storage.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "mongo_exports" {
  name                  = "mongo-exports"
  storage_account_name  = azurerm_storage_account.mongo_storage.name
  container_access_type = "private"
}

# General-purpose storage account (S3-like)
resource "azurerm_storage_account" "general_storage" {
  name                     = var.general_storage_account_name
  resource_group_name      = azurerm_resource_group.mongo_rg.name
  location                 = azurerm_resource_group.mongo_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  enable_https_traffic_only = true

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "general_data" {
  name                  = "data"
  storage_account_name  = azurerm_storage_account.general_storage.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "general_logs" {
  name                  = "logs"
  storage_account_name  = azurerm_storage_account.general_storage.name
  container_access_type = "private"
}
