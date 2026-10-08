variable "aws_region" {
  type = string
  default = "us-east-1"
}

variable "bucket_name" {
  description = "Globally unique bucket name for the application"
  type = string
}

variable "tags" {
  type = map(string)
  default = { managed_by = "terraform", project = "ouros-aws" }
}
