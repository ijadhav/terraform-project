variable "cluster_identifier" {
  type        = string
  description = "The Redshift cluster_identifier."
  default     = ""
}

variable "database_name" {
  type        = string
  description = "The Redshift database_name."
  default     = ""
}

variable "master_username" {
  type        = string
  description = "The Redshift master_username."
  default     = ""
}

variable "master_password" {
  type        = string
  description = "The Redshift master_password."
  default     = ""
}

variable "node_type" {
  type        = string
  description = "The Redshift node_type."
  default     = ""
}

variable "cluster_subnet_group_name" {
  type        = string
  description = "The Redshift cluster_subnet_group_name."
  default     = ""
}

variable "vpc_security_group_ids" {
  type        = list(string)
  description = "The Redshift vpc_security_group_ids."
  default     = []
}

variable "iam_roles" {
  type        = list(string)
  description = "The Redshift iam_roles."
  default     = []
}
