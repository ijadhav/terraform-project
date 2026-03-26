provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "ishi_test" {
  ami           = var.ami_id
  instance_type = var.instance_type
  tags = {
    Name = "ishi_test"
  }

  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    amazon-linux-extras install nginx1 -y
    systemctl start nginx
    systemctl enable nginx
  EOF
}
