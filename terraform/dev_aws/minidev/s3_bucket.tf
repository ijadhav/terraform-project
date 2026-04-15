module "s3_bucket" {
  source = "../../modules/s3_bucket"
  bucket = var.bucket
  tags = local.common_tags
}
