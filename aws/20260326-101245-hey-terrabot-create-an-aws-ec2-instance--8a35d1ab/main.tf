provider "aws" {
  region = "us-east-1"
}

resource "aws_instance" "nginx" {
  ami           = "ami-08c40ec9ead489470" # Amazon Linux 2 AMI (us-east-1)
  instance_type = "t2.micro"

  user_data = <<-EOF
              #!/bin/bash
              sudo amazon-linux-extras install nginx1 -y
              sudo systemctl start nginx
              sudo systemctl enable nginx
              EOF

  tags = {
    Name = "Ishika-test"
  }
}
