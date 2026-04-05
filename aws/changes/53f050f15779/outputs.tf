output "test_instance_id" {
  description = "ID of the test EC2 instance"
  value       = aws_instance.test.id
}

output "test_instance_public_ip" {
  description = "Public IP address of the test EC2 instance"
  value       = aws_instance.test.public_ip
}
