module "redshift" {
  source = "../../modules/redshift"

  cluster_identifier                  = "test"
  database_name                       = var.redshift_database_name
  master_username                     = var.redshift_master_username
  master_password                     = var.redshift_master_password
  node_type                           = var.redshift_node_type
  cluster_type                        = var.redshift_cluster_type
  number_of_nodes                     = var.redshift_number_of_nodes
  iam_roles                           = var.redshift_iam_roles
  publicly_accessible                 = var.redshift_publicly_accessible
  port                                = var.redshift_port
  subnet_ids                          = var.redshift_subnet_ids
  vpc_security_group_ids              = var.redshift_vpc_security_group_ids
  enhanced_vpc_routing                = var.redshift_enhanced_vpc_routing
  allow_version_upgrade               = var.redshift_allow_version_upgrade
  automated_snapshot_retention_period = var.redshift_automated_snapshot_retention_period
  availability_zone                   = var.redshift_availability_zone
  kms_key_id                          = var.redshift_kms_key_id
  logging    = {
    enable                                  = true
    bucket_name                             = var.redshift_logging_bucket_name
    s3_key_prefix                           = var.redshift_logging_s3_key_prefix
    enable_log_exports                      = var.redshift_enable_log_exports
    log_destination_type                    = var.redshift_log_destination_type
    audit_log_destination                   = var.redshift_audit_log_destination
    audit_log_format                        = var.redshift_audit_log_format
    audit_log_enabled                       = var.redshift_audit_log_enabled
    user_activity_log_destination           = var.redshift_user_activity_log_destination
    user_activity_log_format                = var.redshift_user_activity_log_format
    user_activity_log_enabled               = var.redshift_user_activity_log_enabled
    user_log_destination                    = var.redshift_user_log_destination
    user_log_format                         = var.redshift_user_log_format
    user_log_enabled                        = var.redshift_user_log_enabled
    connection_log_destination              = var.redshift_connection_log_destination
    connection_log_format                   = var.redshift_connection_log_format
    connection_log_enabled                  = var.redshift_connection_log_enabled
    user_activity_log_kms_key_id            = var.redshift_user_activity_log_kms_key_id
    user_activity_log_cmk_enabled           = var.redshift_user_activity_log_cmk_enabled
    user_activity_log_grace_period          = var.redshift_user_activity_log_grace_period
    user_activity_log_unencrypted_grace_days = var.redshift_user_activity_log_unencrypted_grace_days
  }
  tags = merge(var.tags, {
    Name = "test"
  })
}
