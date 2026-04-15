module "redshift_cluster" {
  source = "../../modules/redshift_cluster"
  name = var.name
  tags = local.common_tags
  redshift_cluster = var.redshift_cluster
}
