output "instance_id" {
  description = "The ID of the Linux instance."
  value       = aws_instance.linux_vm.id
}
