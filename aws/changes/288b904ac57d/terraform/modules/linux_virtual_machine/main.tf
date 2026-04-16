resource "aws_instance" "linux_vm" {
  ami           = var.ami
  instance_type = var.instance_type
  subnet_id     = var.subnet_id
  vpc_security_group_ids = var.vpc_security_group_ids
  key_name = var.key_name

  tags = var.tags
}
