module "ec2_instance" {
  source = "../../modules/ec2_instance"
}

module "s3_bucket" {
  source = "../../modules/s3_bucket"
}
