variable "cluster_identifier" {
  description = "The Redshift cluster identifier."
  type = string
  default = ""
}

variable "database_name" {
  description = "The name of the first database to be created."
  type = string
  default = ""
}

variable "master_username" {
  description = "The username for the master DB user."
  type = string
  default = ""
}

variable "master_password" {
  description = "The password for the master DB user."
  type = string
  default = ""
}

variable "node_type" {
  description = "The node type to be provisioned for the cluster."
  type = string
  default = ""
}

variable "cluster_subnet_group_name" {
  description = "The name of a subnet group for the cluster."
  type = string
  default = ""
}

variable "vpc_security_group_ids" {
  description = "A list of VPC security group IDs to associate with the cluster."
  type = list(string)
  default = []
}

variable "iam_roles" {
  description = "A list of IAM roles to associate with the cluster."
  type = list(string)
  default = []
}

variable "tags" {
  description = "A map of tags to add to the resource."
  type = map(string)
  default = {}
}
