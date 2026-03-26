provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "ishika_test" {
  ami           = var.ami_id
  instance_type = var.instance_type

  tags = {
    Name = "Ishika-test"
  }
}
