resource "aws_security_group" "this" {
  name        = "${var.name}-sg"
  description = "SG for ${var.name}"
  vpc_id      = aws_vpc.ishika_vpc.id

  # SSH (lock to your IP)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["182.156.35.190/32"]
  }

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS (optional, later)
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-sg" }
}

locals {
  nginx_user_data = <<-EOF
              #!/bin/bash
              set -euxo pipefail
              dnf -y update
              dnf -y install nginx
              systemctl enable nginx
              systemctl start nginx

              cat > /usr/share/nginx/html/index.html <<'HTML'
              <!doctype html>
              <html>
                <head><meta charset="utf-8"><title>HelloIshi</title></head>
                <body style="font-family: Arial; padding: 40px;">
                  <h1>Hello Ishika 👋</h1>
                  <p>This page is hosted on EC2 with NGINX.</p>
                </body>
              </html>
              HTML
              EOF
}
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
# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.ishika_vpc.id
  tags   = { Name = "ishika-igw" }
}

# Public route table
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.ishika_vpc.id
  tags   = { Name = "ishika-public-rt" }
}

# Default route to the internet
resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

# Associate route table with public subnet
resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public_rt.id
}


resource "aws_instance" "this" {
  ami           = var.ami
  instance_type = var.instance_type
  

  subnet_id                   = aws_subnet.public_1.id
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = true
  

  key_name = var.key_name

  user_data = var.enable_nginx ? local.nginx_user_data : null

  tags = { Name = var.name }
}