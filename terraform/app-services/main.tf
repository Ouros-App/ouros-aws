resource "aws_dynamodb_table" "records" {
  name                        = "${var.name_prefix}-records"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = var.partition_key_name
  deletion_protection_enabled = true
  tags                        = var.tags

  attribute {
    name = var.partition_key_name
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name_prefix}-events-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

resource "aws_sqs_queue" "events" {
  name                       = "${var.name_prefix}-events"
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 30
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })
  tags = var.tags
}
