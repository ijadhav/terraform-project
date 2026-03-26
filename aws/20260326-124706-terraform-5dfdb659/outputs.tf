output "vpc_id" {
  description = "ID of the main VPC"
  value       = aws_vpc.main.id
}
