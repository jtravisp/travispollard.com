variable "bucket_name" {
  description = "The name of the S3 bucket"
  type        = string
}

variable "region" {
  description = "AWS Region"
  type        = string
}

variable "cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution associated with this bucket"
  type        = string
}

variable "expire_noncurrent_versions_of" {
  description = <<-EOF2
    Object keys whose previous versions should be deleted a day after they are
    replaced. The bucket is versioned, so an object rewritten every few minutes
    (status.json) would otherwise keep every old copy forever. Each key is its
    own rule with an exact-key prefix, so nothing else in the bucket is touched.
    Empty, the default, creates no lifecycle configuration at all.
  EOF2
  type        = list(string)
  default     = []
}
