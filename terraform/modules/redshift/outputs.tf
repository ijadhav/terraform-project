output "redshift_cluster_identifier" {
  description = "The Redshift cluster identifier."
  value = aws_redshift_cluster.this.id
}
