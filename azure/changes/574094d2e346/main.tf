terraform {
  required_version = ">= 1.0"

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

resource "azurerm_resource_group" "mongodb_rg" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_virtual_network" "mongodb_vnet" {
  name                = "mongodb-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name
}

resource "azurerm_subnet" "mongodb_subnet" {
  name                 = "mongodb-subnet"
  resource_group_name  = azurerm_resource_group.mongodb_rg.name
  virtual_network_name = azurerm_virtual_network.mongodb_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_network_security_group" "mongodb_nsg" {
  name                = "mongodb-nsg"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name

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

resource "azurerm_network_interface" "mongodb_nic" {
  name                = "mongodb-nic"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.mongodb_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.mongodb_public_ip.id
  }
}

resource "azurerm_public_ip" "mongodb_public_ip" {
  name                = "mongodb-public-ip"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface_security_group_association" "mongodb_nic_nsg" {
  network_interface_id      = azurerm_network_interface.mongodb_nic.id
  network_security_group_id = azurerm_network_security_group.mongodb_nsg.id
}

resource "azurerm_linux_virtual_machine" "mongodb_vm" {
  name                = "mongodb-vm"
  resource_group_name = azurerm_resource_group.mongodb_rg.name
  location            = azurerm_resource_group.mongodb_rg.location
  size                = var.vm_size
  admin_username      = var.admin_username
  network_interface_ids = [
    azurerm_network_interface.mongodb_nic.id,
  ]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    name                 = "mongodb-os-disk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "18_04-lts-gen2"
    version   = "latest"
  }

  custom_data = base64encode(<<-EOF
              #!/bin/bash
              apt-get update -y
              apt-get install -y gnupg
              wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | gpg --dearmor | tee /usr/share/keyrings/mongodb-server-6.0.gpg > /dev/null
              echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list
              apt-get update -y
              apt-get install -y mongodb-org
              systemctl enable mongod
              systemctl start mongod
              EOF)
}

resource "azurerm_storage_account" "mongodb_sa" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.mongodb_rg.name
  location                 = azurerm_resource_group.mongodb_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

output "mongodb_vm_public_ip" {
  description = "Public IP address of the MongoDB VM"
  value       = azurerm_public_ip.mongodb_public_ip.ip_address
}

output "mongodb_storage_account_id" {
  description = "Resource ID of the MongoDB storage account"
  value       = azurerm_storage_account.mongodb_sa.id
}
