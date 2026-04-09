module "azure_mongodb_storage" {
  # Source: vena-infrastructure/terraform-azurerm-storage-account
  # Module path: modules/storage
  source = "git@github.com:venasolutions/terraform-azurerm-storage-account.git?ref=v1.0.3"

  suffix = "mongodb"

  resource_group_name = azurerm_resource_group.vena_rg.name
  location            = var.location

  storage_account_name = local.azure_mongodb_storage_name

  # dev and test environments have their own logic for destroying and creating 
  # the MongoDB files that would break in prod, so we handle this using normal 
  # terraform as the shared logic can't live here
  delete_containers = true
  containers = [
    {
      name                  = "cdb-backup"
      container_access_type = "private"
    }
  ]

  edge_zone = var.edge_zone

  tags = merge({
    Owner       = "FND"
    OwnerEmail  = "foundations@venasolutions.com"
    OwnerGithub = "venasolutions/foundations"
  }, var.tags)
}

module "vm_1" {
  # Source: vena-infrastructure/terraform-azurerm-linux-vm (azure_vm)
  # Module path: modules/linux-vm
  source = "git@github.com:venasolutions/terraform-azurerm-linux-vm.git?ref=v5.1.1"

  name                               = "vm1"
  resource_group_name                = azurerm_resource_group.vena_rg.name
  location                           = var.location
  vm_size                            = "Standard_DS1_v2"
  subnet_id                          = data.azurerm_subnet.private[0].id
  admin_username                     = "venasvc"
  disabled_password_authentication   = true
  storage_image_reference_publisher  = "Canonical"
  storage_image_reference_offer      = "0001-com-ubuntu-server-jammy"
  storage_image_reference_sku        = "22_04-lts"
  storage_image_reference_version    = "latest"
  storage_os_disk_name               = "osdisk-VenaDevVm"
  storage_os_disk_caching            = "ReadWrite"
  storage_os_disk_managed_disk_type  = "Premium_LRS"
  storage_os_disk_disk_encryption_set_id = data.azurerm_disk_encryption_set.disk_encryption_set.id
  private_ip_address_allocation_type = "Dynamic"
  remote_port                         = 22
  ssh_public_keys                    = [file("~/.ssh/id_rsa.pub")]

  tags = {
    Environment = var.env
  }
}
