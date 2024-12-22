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
