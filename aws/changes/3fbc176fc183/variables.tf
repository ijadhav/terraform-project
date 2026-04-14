variable "bucket_name" {
  type        = string
  description = "The name of the S3 bucket."
}

variable "enable_logging" {
  type        = bool
  description = "Whether to enable S3 server access logging."
  default     = false
}

variable "enable_versioning" {
  type        = bool
  description = "Whether to enable versioning on the bucket."
  default     = true
}

variable "enable_log_delivery" {
  type        = bool
  description = "Whether to enable the log delivery group."
  default     = false
}

variable "sse_enabled" {
  type        = bool
  description = "Whether to enable server-side encryption."
  default     = true
}

variable "sse_kms_arn" {
  type        = string
  description = "KMS ARN to use for bucket encryption."
  default     = ""
}

variable "bucket_key_enabled" {
  type        = bool
  description = "Whether to enable bucket key for SSE-KMS."
  default     = true
}

variable "glacier_transition_days" {
  type        = number
  description = "Number of days before objects are transitioned to Glacier."
  default     = 90
}

variable "expiration_days" {
  type        = number
  description = "Number of days before objects expire."
  default     = 0
}

variable "noncurrent_version_expiration_days" {
  type        = number
  description = "Number of days before noncurrent object versions expire."
  default     = 90
}

variable "abort_incomplete_multipart_upload_days" {
  type        = number
  description = "Number of days before incomplete multipart uploads are aborted."
  default     = 7
}

variable "log_delivery_canonical_user_id" {
  type        = string
  description = "The canonical user ID for the log delivery group."
  default     = ""
}

variable "bucket_policy_enabled" {
  type        = bool
  description = "Whether to attach a bucket policy."
  default     = true
}

variable "bucket_policy" {
  type        = string
  description = "The bucket policy to apply."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "A map of tags to assign to the resource."
  default     = {}
}
