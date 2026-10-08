provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "site" {
  bucket = var.bucket_name
  force_destroy = false
  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
