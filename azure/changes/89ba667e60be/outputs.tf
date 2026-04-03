output "vm_id" {
  description = "ID of the created Linux VM."
  value       = azurerm_linux_virtual_machine.vm.id
}

output "vm_private_ip" {
  description = "Private IP address of the Linux VM."
  value       = azurerm_network_interface.vm_nic.ip_configuration[0].private_ip_address
}

output "vm_public_ip" {
  description = "Public IP address of the Linux VM (if enabled)."
  value       = var.enable_public_ip ? azurerm_public_ip.vm_pip[0].ip_address : null
}
