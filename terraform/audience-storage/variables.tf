variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "s3_prefix" {
  description = "Must match the service's S3_PREFIX setting."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = { managed_by = "terraform", project = "ouros-aws" }
}
