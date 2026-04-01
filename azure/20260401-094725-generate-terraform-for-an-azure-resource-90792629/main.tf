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

variable "vnet_id" {
  description = "ID of the virtual network hosting the Application Gateway subnets"
  type        = string
}

variable "appgw_subnet_id" {
  description = "Subnet ID dedicated to the Application Gateway"
  type        = string
}

variable "frontend_public_ip_id" {
  description = "Resource ID of the public IP address used by the Application Gateway frontend"
  type        = string
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

module "app_gateway" {
  source = "github.com/your-org/terraform-azurerm-application-gateway//modules/web_app_gw?ref=v1.0.0"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  vnet_id        = var.vnet_id
  subnet_id      = var.appgw_subnet_id
  public_ip_id   = var.frontend_public_ip_id

  application_gateway_name = "agw-${var.business_unit}-${var.project}-${var.environment}-${local.location}"

  frontend_port  = 80
  backend_port   = 80
  protocol       = "Http"

  enable_waf     = true
  waf_mode       = "Prevention"

  tags = local.common_tags
}

output "application_gateway_id" {
  description = "ID of the created Application Gateway"
  value       = module.app_gateway.id
}

output "application_gateway_frontend_ip" {
  description = "Frontend public IP of the Application Gateway (if exposed)"
  value       = module.app_gateway.frontend_public_ip
}
