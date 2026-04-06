output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.example.id
}

output "instance_public_ip" {
  description = "Public IP of the EC2 instance (if associated)"
  value       = aws_instance.example.public_ip
}

output "instance_private_ip" {
  description = "Private IP of the EC2 instance"
  value       = aws_instance.example.private_ip
}

output "http_80_security_group_id" {
  description = "ID of the HTTP 80 security group attached to the instance"
  value       = aws_security_group.http_80.id
}
