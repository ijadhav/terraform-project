output "mongo_storage_account_id" {
  description = "Resource ID of the MongoDB storage account"
  value       = azurerm_storage_account.mongo_storage.id
}

output "mongo_backups_container_name" {
  description = "Name of the MongoDB backups container"
  value       = azurerm_storage_container.mongo_backups.name
}

output "mongo_exports_container_name" {
  description = "Name of the MongoDB exports container"
  value       = azurerm_storage_container.mongo_exports.name
}
