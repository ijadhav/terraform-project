output "instance_1_id" {
  description = "ID of the first EC2 instance"
  value       = aws_instance.example_1.id
}

output "instance_2_id" {
  description = "ID of the second EC2 instance"
  value       = aws_instance.example_2.id
}
