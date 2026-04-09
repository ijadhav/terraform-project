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

module "redshift_cluster" {
  source = "../../modules/redshift_cluster"

  cluster_identifier                  = var.cluster_identifier
  node_type                           = var.node_type
  master_username                     = var.master_username
  master_password                     = var.master_password
  cluster_type                        = var.cluster_type
  publicly_accessible                 = var.publicly_accessible
  skip_final_snapshot                 = var.skip_final_snapshot
  iam_roles                           = var.iam_roles
  vpc_security_group_ids              = var.vpc_security_group_ids
  cluster_subnet_group_name           = var.cluster_subnet_group_name
  encrypted                           = var.encrypted
  kms_key_id                          = var.kms_key_id
  deletion_protection                 = var.deletion_protection
  automated_snapshot_retention_period = var.automated_snapshot_retention_period
  availability_zone_relocation_enabled = var.availability_zone_relocation_enabled
  copy_grants                         = var.copy_grants
  tags                                = var.tags
}
