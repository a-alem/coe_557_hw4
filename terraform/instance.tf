// Key pairs
resource "aws_key_pair" "coe_557_hw4" {
  key_name   = "coe-557-hw4-key"
  public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIqhVdlrpujKWHfH+3Oq7u9LvHAX4r7tAQxx8PiFsXPA coe557 hw4"
}

// Data source for Debian AMI
data "aws_ami" "debian_12" {
  most_recent = true

  owners = ["136693071363"]
  filter {
    name   = "name"
    values = ["debian-12-amd64-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

// Instances EC2
resource "aws_instance" "coe_557_hw4_server" {
  ami = data.aws_ami.debian_12.id
  instance_type = "m8i.2xlarge"
  availability_zone = var.av_zone
  subnet_id = "subnet-046ea35c3305c5095"
  key_name = aws_key_pair.coe_557_hw4.key_name
  source_dest_check = false # Could be problematic with VNFs, so disabling it just in case
  cpu_options {
    nested_virtualization = "enabled"
  }
  root_block_device {
    volume_size           = 200
    volume_type           = "gp3"
    delete_on_termination = true
  }
  vpc_security_group_ids = [
    "sg-09206ea43c7f6aab9"
  ]
  tags = {
    Name = "coe-557-hw4-instance"
  }
}