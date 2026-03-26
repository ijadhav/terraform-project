provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "nginx" {
  ami           = var.ami_id
  instance_type = var.instance_type

  user_data = <<-EOF
              #!/bin/bash
              amazon-linux-extras install -y nginx1
              systemctl enable nginx
              systemctl start nginx
              EOF

  tags = {
    Name = "nginx-instance"
  }
}
