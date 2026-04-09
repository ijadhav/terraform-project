module "azurerm_linux_virtual_machine" {
  source = "git@github.com:venasolutions/tf-azure-linux-vm.git?ref=v1.2.5"

  resource_group_name            = azurerm_resource_group.hub_rg.name
  location                       = var.location
  vm_name                        = "Ishika-test-vm"
  network_interface_id           = module.azurerm_network_interface.primary_nic_id
  size                           = var.size
  custom_data                    = var.custom_data
  admin_username                 = var.admin_username
  admin_ssh_key                  = var.admin_ssh_key
  os_disk                        = var.os_disk
  source_image_reference         = var.source_image_reference
  identity                       = var.identity
  tags                           = merge(var.tags, { environment = "sandbox" })
  eviction_policy                = var.eviction_policy
  priority                       = var.priority
  billing_profile                = var.billing_profile
  maximum_price                  = var.maximum_price
  dedicated_host_id              = var.dedicated_host_id
  additional_unattend_content    = var.additional_unattend_content
  winrm                          = var.winrm
  admin_password                 = var.admin_password
  computer_name                  = var.computer_name
  disable_password_authentication = var.disable_password_authentication
  patch_mode                     = var.patch_mode
  provision_vm_agent             = var.provision_vm_agent
  enable_automatic_updates       = var.enable_automatic_updates
  timezone                       = var.timezone
  additional_capabilities        = var.additional_capabilities
  secret                         = var.secret
  license_type                   = var.license_type
  plan                           = var.plan
  user_data                      = var.user_data
}
