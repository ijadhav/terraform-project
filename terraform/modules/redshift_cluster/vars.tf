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

variable "" {
  type        = string
  description = ""
  default     = ""
}

variable "" {
  type        = number
  description = ""
  default     = 0
}

variable "" {
  type        = bool
  description = ""
  default     = false
}

variable "" {
  type        = list(string)
  description = ""
  default     = []
}
