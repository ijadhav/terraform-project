output "ec2_instance_id" {
  description = "ID of the created EC2 instance."
  value       = module.ec2_instance.id
}

output "ec2_instance_public_ip" {
  description = "Public IP of the EC2 instance, if available."
  value       = module.ec2_instance.public_ip
}

output "s3_bucket_id" {
  description = "ID of the created S3 bucket."
  value       = module.s3_bucket.id
}

output "s3_bucket_arn" {
  description = "ARN of the created S3 bucket."
  value       = module.s3_bucket.arn
}
