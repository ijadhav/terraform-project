output "vm_id" {
  description = "ID of the created Azure VM"
  value       = module.azure_vm.vm_id
}

output "vm_private_ip" {
  description = "Private IP address of the VM"
  value       = azurerm_network_interface.vm_nic.ip_configuration[0].private_ip_address
}

output "vm_public_ip" {
  description = "Public IP address of the VM (if enabled)"
  value       = var.enable_public_ip ? azurerm_public_ip.vm_pip[0].ip_address : null
}
