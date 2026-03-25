provider "aws" {
  region = var.aws_region
}

resource "aws_vpc" "ij_test" {
  name       = var.vpc_name
  cidr_block = var.vpc_cidr
}

resource "aws_subnet" "ij_subnet" {
  vpc_id                  = aws_vpc.ij_test.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
}

resource "aws_security_group" "ij_sg" {
  name        = "ij-sg"
  vpc_id      = aws_vpc.ij_test.id

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "ishika" {
  ami           = var.windows_ami
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.ij_subnet.id
  security_groups = [aws_security_group.ij_sg.name]
  tags = {
    Name = "Ishika"
  }
}
