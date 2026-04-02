output "oracle_vm_id" {
  description = "ID of the Oracle VM"
  value       = azurerm_linux_virtual_machine.oracle_vm.id
}

output "oracle_vm_public_ip" {
  description = "Public IP address of the Oracle VM"
  value       = azurerm_public_ip.oracle_pip.ip_address
}

output "oracle_vm_private_ip" {
  description = "Private IP address of the Oracle VM"
  value       = azurerm_network_interface.oracle_nic.private_ip_address
}
