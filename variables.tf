variable "name" {
  type = string
}

variable "ami" {
  type = string
}
variable "vpc_id" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "subnet_id" {
  type = string
}


variable "key_name" {
  type = string
}

variable "my_ip_cidr" {
  type = string
}

variable "enable_nginx" {
  type    = bool
  default = true
}