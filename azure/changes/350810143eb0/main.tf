terraform {
  required_version = ">= 1.4.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Resource group
resource "azurerm_resource_group" "mongodb_rg" {
  name     = "rg-mongodb-vm"
  location = var.location
}

# Virtual network
resource "azurerm_virtual_network" "mongodb_vnet" {
  name                = "vnet-mongodb"
  address_space       = ["10.10.0.0/16"]
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name
}

# Subnet
resource "azurerm_subnet" "mongodb_subnet" {
  name                 = "snet-mongodb"
  resource_group_name  = azurerm_resource_group.mongodb_rg.name
  virtual_network_name = azurerm_virtual_network.mongodb_vnet.name
  address_prefixes     = ["10.10.1.0/24"]
}

# Public IP
resource "azurerm_public_ip" "mongodb_pip" {
  name                = "pip-mongodb-vm"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# Network security group allowing SSH and MongoDB (27017)
resource "azurerm_network_security_group" "mongodb_nsg" {
  name                = "nsg-mongodb-vm"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name

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

  security_rule {
    name                       = "MongoDB"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "27017"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# Network interface
resource "azurerm_network_interface" "mongodb_nic" {
  name                = "nic-mongodb-vm"
  location            = azurerm_resource_group.mongodb_rg.location
  resource_group_name = azurerm_resource_group.mongodb_rg.name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.mongodb_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.mongodb_pip.id
  }
}

# NSG association
resource "azurerm_network_interface_security_group_association" "mongodb_nic_nsg" {
  network_interface_id      = azurerm_network_interface.mongodb_nic.id
  network_security_group_id = azurerm_network_security_group.mongodb_nsg.id
}

# Linux VM for MongoDB
resource "azurerm_linux_virtual_machine" "mongodb_vm" {
  name                = "vm-mongodb-01"
  resource_group_name = azurerm_resource_group.mongodb_rg.name
  location            = azurerm_resource_group.mongodb_rg.location
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [
    azurerm_network_interface.mongodb_nic.id
  ]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.admin_ssh_public_key
  }

  disable_password_authentication = true

  os_disk {
    name                 = "osdisk-mongodb-01"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-focal"
    sku       = "20_04-lts-gen2"
    version   = "latest"
  }

  # Basic cloud-init script to install and enable MongoDB
  custom_data = base64encode(<<-EOT
              #cloud-config
              package_update: true
              package_upgrade: true
              packages:
                - gnupg
                - curl

              runcmd:
                - curl -fsSL https://pgp.mongodb.com/server-6.0.asc | gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg --dearmor
                - echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list
                - apt-get update
                - apt-get install -y mongodb-org
                - systemctl enable mongod
                - systemctl start mongod

              EOT)
}

output "mongodb_vm_public_ip" {
  description = "Public IP address of the MongoDB VM"
  value       = azurerm_public_ip.mongodb_pip.ip_address
}

output "mongodb_vm_private_ip" {
  description = "Private IP address of the MongoDB VM"
  value       = azurerm_network_interface.mongodb_nic.private_ip_address
}
