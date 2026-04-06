{
  "provider": {
    "azurerm": {
      "features": {}
    }
  },
  "resource": {
    "azurerm_resource_group": {
      "rg": {
        "name": "rg-sandbox",
        "location": "eastus"
      }
    },
    "azurerm_virtual_network": {
      "vnet": {
        "name": "vnet-sandbox",
        "address_space": ["10.20.0.0/16"],
        "location": "eastus",
        "resource_group_name": "rg-sandbox"
      }
    },
    "azurerm_subnet": {
      "subnet": {
        "name": "subnet-sandbox",
        "resource_group_name": "rg-sandbox",
        "virtual_network_name": "vnet-sandbox",
        "address_prefixes": ["10.20.1.0/24"]
      }
    },
    "azurerm_network_interface": {
      "nic": {
        "name": "nic-sandbox",
        "location": "eastus",
        "resource_group_name": "rg-sandbox",
        "ip_configuration": [{
          "name": "internal",
          "subnet_id": "${azurerm_subnet.subnet.id}",
          "private_ip_address_allocation": "Dynamic"
        }]
      }
    },
    "azurerm_linux_virtual_machine": {
      "vm": {
        "name": "vm-sandbox",
        "resource_group_name": "rg-sandbox",
        "location": "eastus",
        "size": "Standard_B2ms",
        "admin_username": "azureuser",
        "network_interface_ids": ["${azurerm_network_interface.nic.id}"],
        "os_disk": {
          "caching": "ReadWrite",
          "storage_account_type": "Standard_LRS"
        },
        "source_image_reference": {
          "publisher": "Canonical",
          "offer": "0001-com-ubuntu-server-jammy",
          "sku": "22_04-lts-gen2",
          "version": "latest"
        }
      }
    }
  }
}
