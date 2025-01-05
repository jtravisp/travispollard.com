variable "default_root_object" {
  description = "The default root object for the CloudFront distribution"
  type        = string
}

variable "origin_domain_name" {
  description = "The domain name of the origin (e.g., S3 bucket or custom domain)"
  type        = string
}

variable "origin_id" {
  description = "The origin ID for the CloudFront distribution"
  type        = string
}

variable "s3_bucket_name" {
  description = "The name of the S3 bucket used as the origin"
  type        = string
  default     = null
}

variable "s3_bucket_domain_name" {
  description = "The domain name of the S3 bucket used as the origin"
  type        = string
  default     = null
}

variable "acm_certificate_arn" {
  description = "The ARN of the ACM certificate for CloudFront"
  type        = string
}
