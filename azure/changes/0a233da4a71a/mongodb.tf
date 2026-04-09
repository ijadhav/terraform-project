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
