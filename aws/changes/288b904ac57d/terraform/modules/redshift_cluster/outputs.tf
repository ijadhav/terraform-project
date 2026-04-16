output "redshift_cluster_id" {
  value       = aws_redshift_cluster.redshift_cluster.id
  description = "The ID of the Redshift cluster."
}
