terraform {
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

# Data source to reference an existing resource group
data "azurerm_resource_group" "rg" {
  name = "1-2b6114da-playground-sandbox"
}

# New resource group in South Central US
resource "azurerm_resource_group" "southcentral_rg" {
  name     = "rg-southcentral-us"
  location = "South Central US"
}

# Example usage of the existing resource group
# Other resources can reference:
#   data.azurerm_resource_group.rg.name
#   data.azurerm_resource_group.rg.location

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-existing-rg"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  address_space       = ["10.1.0.0/16"]
}
