resource "azurerm_resource_group" "rg" {
  name     = "rg-example"
  location = "eastus"

  tags = {
    environment = "dev"
    managed_by  = "terraform"
  }
}
