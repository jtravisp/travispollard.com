data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  tags = {
    Name        = var.bucket_name
    Environment = "Terraform"
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = "*"
        Action = "s3:GetObject"
        Resource = "arn:aws:s3:::${aws_s3_bucket.this.id}/*"
      }
    ]
  })
}

resource "aws_s3_bucket_website_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "error.html"
  }
}

# Only created when a caller asks for it. This resource owns the bucket's whole
# lifecycle configuration: any rule added outside Terraform would be removed on
# the next apply, so add rules here rather than in the console.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count  = length(var.expire_noncurrent_versions_of) > 0 ? 1 : 0
  bucket = aws_s3_bucket.this.id

  dynamic "rule" {
    for_each = var.expire_noncurrent_versions_of
    content {
      id     = "expire-old-versions-${replace(rule.value, "/[^A-Za-z0-9-]/", "-")}"
      status = "Enabled"

      filter {
        prefix = rule.value
      }

      noncurrent_version_expiration {
        noncurrent_days = 1
      }
    }
  }
}
