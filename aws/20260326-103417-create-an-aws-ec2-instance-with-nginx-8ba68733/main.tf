resource "aws_instance" "nginx" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t2.micro"

  user_data = <<-EOF
    #!/bin/bash
    sudo amazon-linux-extras install -y nginx1
    sudo systemctl start nginx
    sudo systemctl enable nginx
  EOF

  tags = {
    Name = "NginxServer"
  }
}
