module "s3" {
  source = "../../modules/s3"

  bucket_name = var.bucket_name
  glacier_transition_days = var.glacier_transition_days
  expiration_days = var.expiration_days
  sse_enabled = var.sse_enabled
  enable_log_delivery = var.enable_log_delivery
  enable_versioning = var.enable_versioning
  enable_logging = var.enable_logging
}
