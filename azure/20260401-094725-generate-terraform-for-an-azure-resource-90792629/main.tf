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

  vnet_name = "vnet-${var.business_unit}-${var.project}-${var.environment}-${local.location}"

  subnet_app_name              = "snet-app-${var.environment}"
  subnet_data_name             = "snet-data-${var.environment}"
  subnet_private_endpoints_name = "snet-pe-${var.environment}"

  # Example CIDR plan; adjust as needed per environment standards
  vnet_address_space       = ["10.10.0.0/16"]
  subnet_app_address_space = "10.10.1.0/24"
  subnet_data_address_space = "10.10.2.0/24"
  subnet_pe_address_space   = "10.10.3.0/24"

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

resource "azurerm_virtual_network" "main" {
  name                = local.vnet_name
  address_space       = local.vnet_address_space
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = local.common_tags
}

# Application subnet (for web/app tiers)
resource "azurerm_subnet" "app" {
  name                 = local.subnet_app_name
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes      = [local.subnet_app_address_space]

  # Typically app subnet allows outbound to internet via firewall/NVA; no private endpoint policies here
}

# Data subnet (for DB, caches, stateful services)
resource "azurerm_subnet" "data" {
  name                 = local.subnet_data_name
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes      = [local.subnet_data_address_space]

  # Often used with NSGs restricting inbound to app subnet only
}

# Dedicated private endpoint subnet (no other resources)
resource "azurerm_subnet" "private_endpoints" {
  name                 = local.subnet_private_endpoints_name
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes      = [local.subnet_pe_address_space]

  enforce_private_link_endpoint_network_policies = true
}

output "vnet_id" {
  description = "ID of the created Virtual Network"
  value       = azurerm_virtual_network.main.id
}

output "subnet_app_id" {
  description = "ID of the application subnet"
  value       = azurerm_subnet.app.id
}

output "subnet_data_id" {
  description = "ID of the data subnet"
  value       = azurerm_subnet.data.id
}

output "subnet_private_endpoints_id" {
  description = "ID of the private endpoints subnet"
  value       = azurerm_subnet.private_endpoints.id
}
