output "test_instance_id" {
  description = "ID of the test EC2 instance"
  value       = aws_instance.test.id
}

output "test_instance_public_ip" {
  description = "Public IP address of the test EC2 instance"
  value       = aws_instance.test.public_ip
}

output "test_s3_bucket_id" {
  description = "ID of the test S3 bucket"
  value       = aws_s3_bucket.test.id
}

output "test_s3_bucket_arn" {
  description = "ARN of the test S3 bucket"
  value       = aws_s3_bucket.test.arn
}
