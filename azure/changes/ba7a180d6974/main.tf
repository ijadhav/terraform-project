terraform {
  required_version = ">= 1.0.0"

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

resource "azurerm_resource_group" "oracle_rg" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_virtual_network" "oracle_vnet" {
  name                = "${var.name_prefix}-vnet"
  address_space       = ["10.10.0.0/16"]
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
}

resource "azurerm_subnet" "oracle_subnet" {
  name                 = "${var.name_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.oracle_rg.name
  virtual_network_name = azurerm_virtual_network.oracle_vnet.name
  address_prefixes     = ["10.10.1.0/24"]
}

resource "azurerm_public_ip" "oracle_pip" {
  name                = "${var.name_prefix}-pip"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_security_group" "oracle_nsg" {
  name                = "${var.name_prefix}-nsg"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Example Oracle listener port (1521). Adjust or remove as needed.
  security_rule {
    name                       = "OracleListener"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "1521"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "oracle_nic" {
  name                = "${var.name_prefix}-nic"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name

  ip_configuration {
    name                          = "${var.name_prefix}-ipcfg"
    subnet_id                     = azurerm_subnet.oracle_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.oracle_pip.id
  }
}

resource "azurerm_network_interface_security_group_association" "oracle_nic_nsg" {
  network_interface_id      = azurerm_network_interface.oracle_nic.id
  network_security_group_id = azurerm_network_security_group.oracle_nsg.id
}

resource "azurerm_linux_virtual_machine" "oracle_vm" {
  name                = "${var.name_prefix}-oracle-vm"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
  size                = var.vm_size

  admin_username                  = var.admin_username
  disable_password_authentication = true

  network_interface_ids = [
    azurerm_network_interface.oracle_nic.id
  ]

  os_disk {
    name                 = "${var.name_prefix}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = var.image_publisher
    offer     = var.image_offer
    sku       = var.image_sku
    version   = var.image_version
  }

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  computer_name = "oraclevm"

  tags = {
    environment = var.environment
    workload    = "oracle-db"
  }
}
