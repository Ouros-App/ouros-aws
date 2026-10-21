provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name             = "ouros-audience-engine-${data.aws_caller_identity.current.account_id}"
  object_prefix           = trim(var.s3_prefix, "/") == "" ? "audiences/" : "${trim(var.s3_prefix, "/")}/audiences/"
  tags                    = merge(var.tags, { service = "audience-engine" })
  access_logs_bucket_name = "${local.bucket_name}-logs-${substr(sha256(local.bucket_name), 0, 6)}"
}

resource "aws_s3_bucket" "audience" {
  bucket        = local.bucket_name
  force_destroy = false
  tags          = local.tags
}

resource "aws_s3_bucket" "access_logs" { # NOSONAR -- terminal log destination; logging it would create recursive S3 log delivery.
  bucket        = local.access_logs_bucket_name
  force_destroy = false
  tags          = merge(local.tags, { purpose = "access-logs" })
}

resource "aws_s3_bucket_public_access_block" "audience" {
  bucket                  = aws_s3_bucket.audience.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket                  = aws_s3_bucket.access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audience" {
  bucket = aws_s3_bucket.audience.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    id     = "expire-access-logs"
    status = "Enabled"

    filter {
      prefix = "${aws_s3_bucket.audience.id}/"
    }

    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_logging" "audience" {
  bucket        = aws_s3_bucket.audience.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "${aws_s3_bucket.audience.id}/"

  depends_on = [aws_s3_bucket_policy.access_logs]
}

resource "aws_s3_bucket_policy" "https_only" {
  bucket = aws_s3_bucket.audience.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.audience.arn,
        "${aws_s3_bucket.audience.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

resource "aws_s3_bucket_policy" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowS3ServerAccessLogs"
        Effect    = "Allow"
        Principal = { Service = "logging.s3.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.access_logs.arn}/${aws_s3_bucket.audience.id}/*"
        Condition = {
          ArnLike      = { "aws:SourceArn" = aws_s3_bucket.audience.arn }
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.access_logs.arn,
          "${aws_s3_bucket.access_logs.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })
}

data "aws_iam_policy_document" "runtime_access" {
  statement {
    sid       = "CheckBucketHealth"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.audience.arn]
  }

  statement {
    sid       = "ReadWriteAudienceObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.audience.arn}/${local.object_prefix}*"]
  }
}
