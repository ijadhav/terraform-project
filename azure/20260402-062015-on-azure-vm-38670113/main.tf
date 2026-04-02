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

resource "azurerm_linux_virtual_machine" "mongo_vm" {
  name                = "vm-mongo"
  location            = azurerm_resource_group.mongo_rg.location
  resource_group_name = azurerm_resource_group.mongo_rg.name
  size                = "Standard_B1s"
  admin_username      = "azureuser"

  network_interface_ids = [
    azurerm_network_interface.mongo_nic.id
  ]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    name                 = "osdisk-mongo-vm"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-focal"
    sku       = "20_04-lts-gen2"
    version   = "latest"
  }

  computer_name  = "mongovm"
  disable_password_authentication = true
}

locals {
  mongo_install_script = <<-EOF
    #!/bin/bash
    set -e

    sudo apt-get update -y
    sudo apt-get install -y gnupg curl

    curl -fsSL https://pgp.mongodb.com/server-6.0.asc | \
      sudo gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg \
      --dearmor

    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | \
      sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list

    sudo apt-get update -y
    sudo apt-get install -y mongodb-org

    sudo systemctl enable mongod
    sudo systemctl start mongod

    # Bind to 0.0.0.0 for demo; in production restrict this
    sudo sed -i 's/bindIp: 127.0.0.1/bindIp: 0.0.0.0/' /etc/mongod.conf
    sudo systemctl restart mongod
  EOF
}

resource "azurerm_virtual_machine_extension" "mongo_install" {
  name                 = "mongodb-install"
  virtual_machine_id   = azurerm_linux_virtual_machine.mongo_vm.id
  publisher            = "Microsoft.Azure.Extensions"
  type                 = "CustomScript"
  type_handler_version = "2.1"

  settings = jsonencode({
    commandToExecute = local.mongo_install_script
  })
}

output "mongo_vm_public_ip" {
  description = "Public IP address of the MongoDB VM"
  value       = azurerm_public_ip.mongo_public_ip.ip_address
}
