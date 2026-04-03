terraform {
  required_version = ">= 1.5.0"

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

# Resource group for the VM
resource "azurerm_resource_group" "vm_rg" {
  name     = var.resource_group_name
  location = var.location

  tags = var.tags
}

# Virtual network
resource "azurerm_virtual_network" "vm_vnet" {
  name                = "vnet-${var.environment}-${var.location}"
  address_space       = [var.vnet_address_space]
  location            = azurerm_resource_group.vm_rg.location
  resource_group_name = azurerm_resource_group.vm_rg.name

  tags = var.tags
}

# Subnet for the VM
resource "azurerm_subnet" "vm_subnet" {
  name                 = "snet-${var.environment}-vm"
  resource_group_name  = azurerm_resource_group.vm_rg.name
  virtual_network_name = azurerm_virtual_network.vm_vnet.name
  address_prefixes     = [var.subnet_address_prefix]
}

# Network security group for the VM subnet (SSH only)
resource "azurerm_network_security_group" "vm_nsg" {
  name                = "nsg-${var.environment}-vm"
  location            = azurerm_resource_group.vm_rg.location
  resource_group_name = azurerm_resource_group.vm_rg.name

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.ssh_source_cidr
    destination_address_prefix = "*"
  }

  tags = var.tags
}

resource "azurerm_subnet_network_security_group_association" "vm_subnet_nsg" {
  subnet_id                 = azurerm_subnet.vm_subnet.id
  network_security_group_id = azurerm_network_security_group.vm_nsg.id
}

# Public IP for the VM (can be disabled via variable)
resource "azurerm_public_ip" "vm_pip" {
  count               = var.enable_public_ip ? 1 : 0
  name                = "pip-${var.environment}-vm"
  location            = azurerm_resource_group.vm_rg.location
  resource_group_name = azurerm_resource_group.vm_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = var.tags
}

# Network interface for the VM
resource "azurerm_network_interface" "vm_nic" {
  name                = "nic-${var.environment}-vm"
  location            = azurerm_resource_group.vm_rg.location
  resource_group_name = azurerm_resource_group.vm_rg.name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.vm_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = var.enable_public_ip ? azurerm_public_ip.vm_pip[0].id : null
  }

  tags = var.tags
}

# Azure VM using existing internal VM module (pattern-aligned with VM scale set module usage)【8:0†source】
module "azure_vm" {
  # Example internal module source; adjust ref/version as needed
  # source = "git@github.com:venasolutions/tf-azure-vm.git?ref=v1.0.0"
  source = "../tf-azure-vm"

  resource_group_name = azurerm_resource_group.vm_rg.name
  location            = azurerm_resource_group.vm_rg.location

  vm_name               = "vm-${var.environment}-${var.location}"
  network_interface_ids = [azurerm_network_interface.vm_nic.id]

  os_flavor               = "linux"
  linux_distribution_name = var.linux_distribution_name

  vm_size = var.vm_size

  # SSH configuration
  generate_admin_ssh_key = var.generate_admin_ssh_key
  admin_ssh_key_data     = var.generate_admin_ssh_key ? null : var.admin_ssh_key_data

  # Additional data disks (optional, can be empty)
  additional_data_disks = var.additional_data_disks

  # Tags
  tags = var.tags
}

output "vm_id" {
  description = "ID of the created Azure VM"
  value       = module.azure_vm.vm_id
}

output "vm_private_ip" {
  description = "Private IP address of the VM"
  value       = azurerm_network_interface.vm_nic.ip_configuration[0].private_ip_address
}

output "vm_public_ip" {
  description = "Public IP address of the VM (if enabled)"
  value       = var.enable_public_ip ? azurerm_public_ip.vm_pip[0].ip_address : null
}
