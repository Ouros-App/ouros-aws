variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  description = "Unique prefix used for the DynamoDB table and SQS queues"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-40 lowercase letters, numbers, or hyphens, and start/end with a letter or number."
  }
}

variable "partition_key_name" {
  description = "String partition key attribute for the DynamoDB table"
  type        = string
  default     = "id"

  validation {
    condition     = length(var.partition_key_name) > 0 && length(var.partition_key_name) <= 255
    error_message = "partition_key_name must contain 1-255 characters."
  }
}

variable "tags" {
  type = map(string)
  default = {
    managed_by = "terraform"
    project    = "ouros-aws"
  }
}
