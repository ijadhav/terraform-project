resource "aws_vpc" "ishika_vpc"{
     cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "ishika_vpc" }

}

resource "aws_subnet" "public_1" {
  vpc_id            = aws_vpc.ishika_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"   # <-- AZ here

  map_public_ip_on_launch = true
}

module "web" {
  source = "./modules/ec2_nginx"

  name          = "HelloIshi"
  ami           = "ami-02dfbd4ff395f2a1b"
  instance_type = "t3.small"

  subnet_id = aws_subnet.public_1.id
  vpc_id = aws_vpc.ishika_vpc.id

  key_name   = var.key_name
  my_ip_cidr = var.my_ip_cidr

  enable_nginx = true
}