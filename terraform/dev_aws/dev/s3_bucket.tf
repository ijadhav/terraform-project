module "s3_bucket" {
  source     = "../../modules/s3_bucket"
  name       = var.name
  tags       = local.common_tags
  protected  = var.protected
}
