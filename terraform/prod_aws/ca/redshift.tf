module "redshift" {
  source     = "../../modules/redshift"
  name       = "test"
  tags       = local.common_tags
  protected  = var.protected
}
