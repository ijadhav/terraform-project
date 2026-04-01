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

variable "environment" {
  description = "Deployment environment (e.g. dev, test, prod)"
  type        = string
  default     = "dev"
}

variable "business_unit" {
  description = "Owning business unit"
  type        = string
  default     = "core"
}

variable "project" {
  description = "Project or application name"
  type        = string
  default     = "example-app"
}

locals {
  location            = "westeurope"
  resource_group_name = "rg-${var.business_unit}-${var.project}-${var.environment}-${local.location}"

  common_tags = {
    environment   = var.environment
    business_unit = var.business_unit
    project       = var.project
    location      = local.location
    managed_by    = "terraform"
  }
}

resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = local.location

  tags = local.common_tags
}

output "resource_group_name" {
  description = "Name of the created resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the created resource group"
  value       = azurerm_resource_group.main.location
}
