variable "cluster_identifier" {
  description = "The identifier for the Redshift cluster."
  type = string
}

variable "database_name" {
  description = "The name of the first database to be created when the cluster is created."
  type = string
}

variable "master_username" {
  description = "Username for the master DB user."
  type = string
}

variable "master_password" {
  description = "Password for the master DB user."
  type = string
  sensitive = true
}

variable "node_type" {
  description = "The node type to be provisioned for the cluster."
  type = string
}

variable "cluster_subnet_group_name" {
  description = "The name of a subnet group for the cluster."
  type = string
}

variable "vpc_security_group_ids" {
  description = "A list of Virtual Private Cloud (VPC) security group IDs to be associated with the cluster."
  type = list(string)
}

variable "iam_roles" {
  description = "A list of IAM roles to associate with the cluster."
  type = list(string)
}

variable "tags" {
  description = "A map of tags to assign to the resource."
  type = map(string)
}
