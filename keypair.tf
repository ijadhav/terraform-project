resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
resource "aws_key_pair" "ishika" {
  key_name   = "ishika-key"
  public_key = tls_private_key.ssh.public_key_openssh
}

# Write the private key to a local .pem file
resource "local_file" "pem" {
  filename        = "$Downloads/ishika-key.pem"
  content         = tls_private_key.ssh.private_key_pem
  file_permission = "0600"
}