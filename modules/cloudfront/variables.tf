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

# ---------------------------------------------------------------------------
# Extra origins and behaviors
# ---------------------------------------------------------------------------
# This module is shared, so the second origin arrives as data rather than as a
# hardcoded "cfb". The module knows nothing about football and stays reusable
# for the next subpage that needs its own bucket.
#
# Both default to empty, so a caller that passes neither gets exactly the
# distribution it had before these variables existed. That is what makes this
# change safe to apply to a live distribution: the dynamic blocks below produce
# no blocks at all until something is passed in.

variable "extra_origins" {
  description = <<-EOT
    Additional S3 origins reached through an Origin Access Control. No
    custom_origin_config: these are REST endpoints signed with SigV4, unlike the
    site bucket, which is a website endpoint behind a custom origin.
  EOT

  type = list(object({
    origin_id   = string
    domain_name = string
    oac_id      = string
  }))
  default = []
}

variable "extra_behaviors" {
  description = <<-EOT
    Ordered cache behaviors, evaluated before the default one in list order.
    Each carries its own cache_policy_id: a shared module has no business
    assuming two subpages want the same caching, and the alternative was a
    third variable holding one policy for all of them.
  EOT

  type = list(object({
    path_pattern     = string
    target_origin_id = string
    cache_policy_id  = string
  }))
  default = []
}
