resource "aws_redshift_cluster" "this" {
  cluster_identifier = var.cluster_identifier
  database_name = var.database_name
  master_username = var.master_username
  master_password = var.master_password
  node_type = var.node_type
  cluster_subnet_group_name = var.cluster_subnet_group_name
  vpc_security_group_ids = var.vpc_security_group_ids
  iam_roles = var.iam_roles
  tags = var.tags
}
