terraform {
  required_version = ">= 1.3.0"

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

# Resource group for the Oracle VM
resource "azurerm_resource_group" "oracle_rg" {
  name     = var.resource_group_name
  location = var.location
}

# Virtual network
resource "azurerm_virtual_network" "oracle_vnet" {
  name                = "${var.prefix}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
}

# Subnet
resource "azurerm_subnet" "oracle_subnet" {
  name                 = "${var.prefix}-subnet"
  resource_group_name  = azurerm_resource_group.oracle_rg.name
  virtual_network_name = azurerm_virtual_network.oracle_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Public IP for the VM (can be disabled in production)
resource "azurerm_public_ip" "oracle_pip" {
  name                = "${var.prefix}-pip"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# Network security group
resource "azurerm_network_security_group" "oracle_nsg" {
  name                = "${var.prefix}-nsg"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name

  security_rule {
    name                       = "Allow-SSH"
    priority                   = 1000
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Example Oracle listener port (default 1521); tighten source in real use
  security_rule {
    name                       = "Allow-Oracle-Listener"
    priority                   = 1010
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "1521"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# Network interface
resource "azurerm_network_interface" "oracle_nic" {
  name                = "${var.prefix}-nic"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.oracle_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.oracle_pip.id
  }
}

# Associate NIC with NSG
resource "azurerm_network_interface_security_group_association" "oracle_nic_nsg" {
  network_interface_id      = azurerm_network_interface.oracle_nic.id
  network_security_group_id = azurerm_network_security_group.oracle_nsg.id
}

# Managed disk for Oracle data (separate from OS disk)
resource "azurerm_managed_disk" "oracle_data_disk" {
  name                 = "${var.prefix}-oracle-data"
  location             = azurerm_resource_group.oracle_rg.location
  resource_group_name  = azurerm_resource_group.oracle_rg.name
  storage_account_type = "Premium_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.oracle_data_disk_size_gb
}

# Linux VM to host Oracle (OS image is a generic Oracle Linux example)
resource "azurerm_linux_virtual_machine" "oracle_vm" {
  name                = "test-ishika"
  location            = azurerm_resource_group.oracle_rg.location
  resource_group_name = azurerm_resource_group.oracle_rg.name
  size                = var.vm_size

  admin_username = var.admin_username

  network_interface_ids = [
    azurerm_network_interface.oracle_nic.id,
  ]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    name                 = "${var.prefix}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = "Oracle"
    offer     = "Oracle-Linux"
    sku       = "ol86-lvm"
    version   = "latest"
  }

  computer_name                = "test-ishika"
  disable_password_authentication = true
}

# Attach data disk to the VM for Oracle database files
resource "azurerm_virtual_machine_data_disk_attachment" "oracle_data_attach" {
  managed_disk_id    = azurerm_managed_disk.oracle_data_disk.id
  virtual_machine_id = azurerm_linux_virtual_machine.oracle_vm.id
  lun                = 0
  caching            = "ReadWrite"
}

output "oracle_vm_public_ip" {
  description = "Public IP address of the Oracle VM"
  value       = azurerm_public_ip.oracle_pip.ip_address
}

output "oracle_vm_private_ip" {
  description = "Private IP address of the Oracle VM"
  value       = azurerm_network_interface.oracle_nic.private_ip_address
}
