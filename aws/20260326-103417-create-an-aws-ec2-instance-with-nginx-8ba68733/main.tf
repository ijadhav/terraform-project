resource "aws_instance" "nginx" {
  ami           = "ami-08541b76eeb39c6e7"
  instance_type = "t2.micro"

  user_data = <<-EOF
    #!/bin/bash
    # No additional setup commands
  EOF

  tags = {
    Name = "UbuntuServer"
  }
}
