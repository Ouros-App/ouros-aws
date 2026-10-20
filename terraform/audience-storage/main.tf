provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name   = "ouros-audience-engine-${data.aws_caller_identity.current.account_id}"
  object_prefix = trim(var.s3_prefix, "/") == "" ? "audiences/" : "${trim(var.s3_prefix, "/")}/audiences/"
  tags          = merge(var.tags, { service = "audience-engine" })
}

resource "aws_s3_bucket" "audience" {
  bucket        = local.bucket_name
  force_destroy = false
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "audience" {
  bucket                  = aws_s3_bucket.audience.id
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
