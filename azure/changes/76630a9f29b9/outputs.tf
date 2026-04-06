output "resource_group_name" {
  description = "Name of the created resource group"
  value       = azurerm_resource_group.main.name
}

output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.main.id
}

output "storage_account_primary_connection_string" {
  description = "Primary connection string for the storage account"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "cosmos_mongo_account_id" {
  description = "ID of the Cosmos DB MongoDB account"
  value       = azurerm_cosmosdb_account.mongo.id
}

output "cosmos_mongo_endpoint" {
  description = "Endpoint of the Cosmos DB MongoDB account"
  value       = azurerm_cosmosdb_account.mongo.endpoint
}
