variable "bucket" {
  description = "The name of the S3 bucket."
}

variable "tags" {
  description = "A map of tags to assign to the resources."
  type = map(string)
  default = {}
}
