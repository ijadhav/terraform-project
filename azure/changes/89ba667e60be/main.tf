terraform {
  required_version = ">= 1.6.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.3.0, < 5.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
    }
  }
}

provider "azurerm" {
  features {}
}

locals {
  location          = var.location
  resource_group    = var.resource_group_name
  vm_name           = "vm-${var.subscription_type}-${var.env}-${var.location}"
  nic_name          = "nic-${var.subscription_type}-${var.env}-${var.location}"
  public_ip_name    = "pip-${var.subscription_type}-${var.env}-${var.location}"
  network_secgrp    = "nsg-${var.subscription_type}-${var.env}-${var.location}"
  subnet_id         = var.subnet_id
  admin_username    = "venaadmin"
  tags = merge(
    {
      ProjectName = var.project_name
      Env         = var.env
      Owner       = var.owner
      repo        = var.repo
    },
    var.additional_tags
  )
}

resource "random_id" "vm" {
  byte_length = 4
}

resource "azurerm_network_security_group" "vm_nsg" {
  name                = local.network_secgrp
  location            = local.location
  resource_group_name = local.resource_group

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.ssh_source_address_prefix
    destination_address_prefix = "*"
  }

  tags = local.tags
}

resource "azurerm_network_interface" "vm_nic" {
  name                = local.nic_name
  location            = local.location
  resource_group_name = local.resource_group

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = var.enable_public_ip ? azurerm_public_ip.vm_pip[0].id : null
  }

  tags = local.tags
}

resource "azurerm_network_interface_security_group_association" "vm_nic_nsg" {
  network_interface_id      = azurerm_network_interface.vm_nic.id
  network_security_group_id = azurerm_network_security_group.vm_nsg.id
}

resource "azurerm_public_ip" "vm_pip" {
  count               = var.enable_public_ip ? 1 : 0
  name                = local.public_ip_name
  location            = local.location
  resource_group_name = local.resource_group
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
}

resource "azurerm_linux_virtual_machine" "vm" {
  name                = local.vm_name
  resource_group_name = local.resource_group
  location            = local.location
  size                = var.vm_size

  admin_username = local.admin_username

  disable_password_authentication = true

  admin_ssh_key {
    username   = local.admin_username
    public_key = var.admin_ssh_public_key
  }

  network_interface_ids = [
    azurerm_network_interface.vm_nic.id
  ]

  os_disk {
    name                 = "osdisk-${local.vm_name}-${random_id.vm.hex}"
    caching              = "ReadWrite"
    storage_account_type = var.os_disk_storage_account_type
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = var.image_publisher
    offer     = var.image_offer
    sku       = var.image_sku
    version   = var.image_version
  }

  tags = local.tags
}
