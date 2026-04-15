module "vena_datacentre" {
  source = "../../modules/vena_datacentre"

  env = local.env
  subdomain = "us1"
  subdomain_override = "us1"
  subdomain_short = "us1b"
  private_subnet_names = [
    "${local.env}_app_1",
    "${local.env}_app_2"
  ]
  rds_subnet_names = [
    "${local.env}_app_1",
    "${local.env}_app_2"
  ]
  private_subnets = [
    {
      name = "${local.env}_app_1"
      cidr = "${local.network_base}.2.0/24"
      az = "${local.region}b"
    },
    {
      name = "${local.env}_app_2"
      cidr = "${local.network_base}.3.0/24"
      az = "${local.region}c"
    }
  ]
  public_subnets = [
    {
      name = "${local.env}_app_gw_1"
      cidr = "${local.network_base}.10.0/24"
      az = "${local.region}b"
    },
    {
      name = "${local.env}_app_gw_2"
      cidr = "${local.network_base}.11.0/24"
      az = "${local.region}c"
    }
  ]
  tgw_subnets = [
    {
      name = "${local.env}_tgw_1"
      cidr = "${local.network_base}.255.0/28"
      az = "${local.region}b"
    },
    {
      name = "${local.env}_tgw_2"
      cidr = "${local.network_base}.255.16/28"
      az = "${local.region}c"
    }
  ]
  redshift_subnet_names = ["${local.env}_app_1"]
  cidr = "${local.network_base}.0.0/16"
  lb_number_of_public_subnets = 2
  redshift_historical_storage_buckets = [
    "arn:aws:s3:::venacloud-statestreet-redshift-historical-virginia"
  ]
  source_account_id = local.source_account_id
  create_subdomain_dns = true
  high_priority_alert_sns = local.high_priority_alert_sns
  low_priority_alert_sns = local.low_priority_alert_sns
  builds_bucket = local.builds_bucket
  production = true
  create_rabbitmq_lb = true
  create_venacloud_presentation_bucket = false
  ecs_patch_override_list_bucket_arns_override = [
    "arn:aws:s3:::venacloud-patch-override-lists-prod-ss"
  ]
  ecr_arn_prefix = "arn:aws:ecr:us-west-1:${local.source_account_id}"
}
