resource "azurerm_linux_virtual_machine" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  network_interface_ids = var.network_interface_ids
  size                = var.size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
}
