module "s3_bucket" {
  source = "../../modules/s3_bucket"
  bucket = "test"
  tags = local.common_tags
}
