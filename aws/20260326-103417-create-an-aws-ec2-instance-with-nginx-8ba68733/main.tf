resource "aws_vpc" "custom_vpc" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "test-vpc"
  }
}

resource "aws_subnet" "custom_subnet" {
  vpc_id            = aws_vpc.custom_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
  tags = {
    Name = "CustomSubnet"
  }
}

resource "aws_instance" "nginx" {
  ami           = "ami-08541b76eeb39c6e7"
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.custom_subnet.id
  user_data = <<-EOF
    #!/bin/bash
    # No additional setup commands
  EOF
  tags = {
    Name = "Ishika"
  }
}

resource "aws_s3_bucket" "storage_bucket" {
  bucket = "my-storage-bucket-1234"
  acl    = "private"
  tags = {
    Name = "StorageBucket"
  }
}
