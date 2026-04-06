{
  "provider": {
    "azurerm": {
      "features": {}
    }
  },
  "resource": {
    "azurerm_resource_group": {
      "rg": {
        "name": "rg-default",
        "location": "eastus"
      }
    },
    "azurerm_virtual_network": {
      "vnet": {
        "name": "vnet-default",
        "address_space": ["10.10.0.0/16"],
        "location": "eastus",
        "resource_group_name": "rg-default"
      }
    },
    "azurerm_subnet": {
      "subnet": {
        "name": "subnet-default",
        "resource_group_name": "rg-default",
        "virtual_network_name": "vnet-default",
        "address_prefixes": ["10.10.1.0/24"]
      }
    },
    "azurerm_network_interface": {
      "nic": {
        "name": "nic-default",
        "location": "eastus",
        "resource_group_name": "rg-default",
        "ip_configuration": [{
          "name": "internal",
          "subnet_id": "${azurerm_subnet.subnet.id}",
          "private_ip_address_allocation": "Dynamic"
        }]
      }
    },
    "azurerm_linux_virtual_machine": {
      "vm": {
        "name": "vm-default",
        "resource_group_name": "rg-default",
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
