variable "name" {
  description = "The name of the VM."
}

variable "resource_group_name" {
  description = "The resource group name."
}

variable "location" {
  description = "Azure location."
}

variable "network_interface_ids" {
  type = list(string)
  description = "NICs for the VM."
}

variable "size" {
  description = "VM size."
}

variable "admin_username" {
  description = "Admin username."
}

variable "admin_password" {
  description = "Admin password."
}
