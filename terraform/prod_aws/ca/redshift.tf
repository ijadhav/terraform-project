module "redshift" {
  source     = "../../modules/redshift"
  name       = var.name
  tags       = local.common_tags
  protected  = var.protected
}
