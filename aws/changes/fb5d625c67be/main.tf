terraform {
  required_version = ">= 1.3.0"
}

module "ec2" {
  source = "../../modules/ec2"

  name                = "ec2-vena-standards"
  environment         = "dev"
  ssh_key_name        = "kp-platform-dev"
  allowed_account_ids = ["111111111111"]
  region              = "us-east-1"
  additional_tags     = { change_ticket = "CHG-1234" }
}
