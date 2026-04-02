terraform {
  required_version = ">= 1.3.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "mongo_rg" {
  name     = "rg-mongo-vm"
  location = "eastus"
}

resource "azurerm_virtual_network" "mongo_vnet" {
  name                = "vnet-mongo"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.mongo_rg.location
  resource_group_name = azurerm_resource_group.mongo_rg.name
}

resource "azurerm_subnet" "mongo_subnet" {
  name                 = "snet-mongo"
  resource_group_name  = azurerm_resource_group.mongo_rg.name
  virtual_network_name = azurerm_virtual_network.mongo_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_network_security_group" "mongo_nsg" {
  name                = "nsg-mongo"
  location            = azurerm_resource_group.mongo_rg.location
  resource_group_name = azurerm_resource_group.mongo_rg.name

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "0.0.0.0/0"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "MongoDB"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "27017"
    source_address_prefix      = "0.0.0.0/0"
    destination_address_prefix = "*"
  }
}

resource "azurerm_public_ip" "mongo_public_ip" {
  name                = "pip-mongo-vm"
  location            = azurerm_resource_group.mongo_rg.location
  resource_group_name = azurerm_resource_group.mongo_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "mongo_nic" {
  name                = "nic-mongo-vm"
  location            = azurerm_resource_group.mongo_rg.location
  resource_group_name = azurerm_resource_group.mongo_rg.name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.mongo_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.mongo_public_ip.id
  }
}

resource "azurerm_network_interface_security_group_association" "mongo_nic_nsg" {
  network_interface_id      = azurerm_network_interface.mongo_nic.id
  network_security_group_id = azurerm_network_security_group.mongo_nsg.id
}
