module "ec2_test" {
  source = "../../modules/ec2-instance"

  instance_name                  = "test"
  subnet_id                      = var.subnet_id
  iam_instance_profile           = var.iam_instance_profile
  instance_type                  = var.instance_type
  ebs_optimized                  = var.ebs_optimized
  monitoring                     = var.monitoring
  enable_volume_tags             = var.enable_volume_tags
  ami                            = var.ami
  private_ip                     = var.private_ip
  vpc_security_group_ids         = var.vpc_security_group_ids
  user_data                      = var.user_data
  root_block_device              = var.root_block_device
  create_eni                     = var.create_eni
  eni_delete_on_termination      = var.eni_delete_on_termination
  eni_device_index               = var.eni_device_index
  eni_security_groups            = var.eni_security_groups
  enable_termination_protection  = var.enable_termination_protection
  disable_api_stop               = var.disable_api_stop
  disable_api_termination        = var.disable_api_termination
  tags                           = var.tags
}
