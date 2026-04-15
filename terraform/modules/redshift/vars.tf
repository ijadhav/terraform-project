variable "name" {
  type        = string
  description = "Name for the redshift resource."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to the redshift resource."
  default     = {}
}

variable "protected" {
  type        = bool
  description = "Whether to enable delete protection for this redshift resource."
  default     = false
}
