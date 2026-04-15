variable "name" {
  type        = string
  description = "Name for the redshift_cluster resource."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to the redshift_cluster resource."
  default     = {}
}

variable "redshift_cluster" {
  type        = string
  description = "redshift_cluster for the redshift_cluster resource."
  default     = ""
}
