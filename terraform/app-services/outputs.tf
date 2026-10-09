output "dynamodb_table_name" {
  value = aws_dynamodb_table.records.name
}

output "events_queue_url" {
  value = aws_sqs_queue.events.url
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dead_letter.url
}
