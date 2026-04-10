module "storage_bucket" {
  source = "../../modules/s3_bucket"

  bucket_name                            = var.bucket_name
  enable_logging                         = var.enable_logging
  enable_versioning                      = var.enable_versioning
  enable_log_delivery                    = var.enable_log_delivery
  sse_enabled                            = var.sse_enabled
  sse_kms_arn                            = var.sse_kms_arn
  bucket_key_enabled                     = var.bucket_key_enabled
  glacier_transition_days                = var.glacier_transition_days
  expiration_days                        = var.expiration_days
  noncurrent_version_expiration_days     = var.noncurrent_version_expiration_days
  abort_incomplete_multipart_upload_days = var.abort_incomplete_multipart_upload_days
  log_delivery_canonical_user_id         = var.log_delivery_canonical_user_id
  bucket_policy_enabled                  = var.bucket_policy_enabled
  bucket_policy                          = var.bucket_policy

  tags = merge(
    var.tags,
    {
      Name = var.bucket_name
    },
  )
}
