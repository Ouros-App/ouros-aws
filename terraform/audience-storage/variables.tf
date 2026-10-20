variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "s3_prefix" {
  description = "Must match the service's S3_PREFIX setting."
  type        = string
  default     = ""

  validation {
    condition     = length(regexall("[*?]", var.s3_prefix)) == 0
    error_message = "s3_prefix must not contain '*' or '?' because IAM treats them as wildcards."
  }
}

variable "tags" {
  type    = map(string)
  default = { managed_by = "terraform", project = "ouros-aws" }
}
