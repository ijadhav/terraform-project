module "ec2_instance" {
  source = "../../modules/ec2_instance"

  instance_type               = var.instance_type
  subnet_id                    = var.subnet_id
  vpc_id                       = var.vpc_id
  iam_instance_profile         = var.iam_instance_profile
  key_name                     = var.key_name
  monitoring                   = var.monitoring
  disable_api_termination      = var.disable_api_termination
  ebs_optimized                = var.ebs_optimized
  private_ip                   = var.private_ip
  source_dest_check            = var.source_dest_check
  additional_eni               = var.additional_eni
  additional_eni_device_index  = var.additional_eni_device_index
  additional_eni_subnet_id     = var.additional_eni_subnet_id
  additional_eni_security_groups = var.additional_eni_security_groups
  create_eni                   = var.create_eni
  root_block_device            = var.root_block_device
  ebs_block_device             = var.ebs_block_device
  user_data                    = var.user_data
  ami                          = var.ami
  tags                         = var.tags
}
