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

output "general_storage_account_id" {
  description = "Resource ID of the general purpose storage account"
  value       = azurerm_storage_account.general_storage.id
}

output "general_data_container_name" {
  description = "Name of the general data container"
  value       = azurerm_storage_container.general_data.name
}

output "general_logs_container_name" {
  description = "Name of the general logs container"
  value       = azurerm_storage_container.general_logs.name
}
