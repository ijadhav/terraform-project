module "ec2_instance" {
  source = var.ec2_module_source

  name          = var.ec2_instance_name
  instance_type = var.ec2_instance_type
  aws_region    = var.aws_region
  user_data     = var.ec2_user_data
}
