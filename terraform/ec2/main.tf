# Deliberately no EC2 resources yet: Learner Lab permissions, approved AMI,
# network, key pair and instance size must be confirmed before provisioning.
provider "aws" {
  region = var.aws_region
}
