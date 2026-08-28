# Additions to the EXISTING root Terraform (the site stack).
#
# Changed from the previous draft:
#   - path_pattern is /cfb/data/* rather than /cfb/*, because the pages are
#     now Next.js routes served from the site bucket like every other route.
#   - The CloudFront Function is gone. Next's static export already emits
#     cfb/index.html and cfb/accuracy/index.html, so the default behavior
#     handles directory indexes with no rewriting.
#
# The contract between the two stacks:
#   root  ->  cfb  : distribution id + arn, via SSM
#   cfb   ->  root : nothing. The bucket name is a shared constant.

variable "cfb_data_bucket_name" {
  description = "Name of the football project's data bucket. Must match the value in cfb/terraform."
  type        = string
  default     = "travispollard-cfb-data"
}

data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# Deferred to Phase 1
# ---------------------------------------------------------------------------
# SPEC-phase0 section 10.2: Phase 0 adds ONLY the two aws_ssm_parameter
# resources at the bottom of this file. Phase 0 has no reason to touch the
# live distribution -- there is no JSON to serve yet.
#
# The OAC below is a real resource: left uncommented it gets CREATED on the
# next root apply, ahead of the behavior that would use it. It is commented
# out rather than deleted so the design survives to Phase 1, alongside the
# distribution changes sketched further down. The cache policy lookup goes
# with it -- nothing references it until those changes land, and a live data
# source is an AWS call on every plan.
#
# Uncomment both when the /cfb/data/* behavior is wired up.

# data "aws_cloudfront_cache_policy" "optimized" {
#   name = "Managed-CachingOptimized"
# }

locals {
  cfb_data_origin_id = "cfb-data-s3"

  # Referenced by convention rather than by data source or remote state, so
  # this stack has no dependency on cfb/terraform. CloudFront does not
  # validate the origin at create time.
  cfb_data_origin_domain = "${var.cfb_data_bucket_name}.s3.${data.aws_region.current.name}.amazonaws.com"
}

# resource "aws_cloudfront_origin_access_control" "cfb_data" {
#   name                              = "cfb-data-oac"
#   description                       = "OAC for the college football data bucket"
#   origin_access_control_origin_type = "s3"
#   signing_behavior                  = "always"
#   signing_protocol                  = "sigv4"
# }

# ---------------------------------------------------------------------------
# Distribution changes
# ---------------------------------------------------------------------------
# Since modules/cloudfront is shared, take these as variables rather than
# hardcoding "cfb" into the module. Something like:
#
#   variable "extra_origins" {
#     type = list(object({
#       origin_id   = string
#       domain_name = string
#       oac_id      = string
#     }))
#     default = []
#   }
#
#   variable "extra_behaviors" {
#     type = list(object({
#       path_pattern     = string
#       target_origin_id = string
#     }))
#     default = []
#   }
#
# Then the module knows nothing about football and is reusable for the next
# subpage. Inside the module, alongside the existing origin and
# default_cache_behavior:
#
#   dynamic "origin" {
#     for_each = var.extra_origins
#     content {
#       domain_name              = origin.value.domain_name
#       origin_id                = origin.value.origin_id
#       origin_access_control_id = origin.value.oac_id
#     }
#   }
#
#   dynamic "ordered_cache_behavior" {
#     for_each = var.extra_behaviors
#     content {
#       path_pattern           = ordered_cache_behavior.value.path_pattern
#       target_origin_id       = ordered_cache_behavior.value.target_origin_id
#       allowed_methods        = ["GET", "HEAD", "OPTIONS"]
#       cached_methods         = ["GET", "HEAD"]
#       viewer_protocol_policy = "redirect-to-https"
#       compress               = true
#       cache_policy_id        = var.extra_cache_policy_id
#     }
#   }
#
# And at the root, passing in:
#
#   extra_origins = [{
#     origin_id   = local.cfb_data_origin_id
#     domain_name = local.cfb_data_origin_domain
#     oac_id      = aws_cloudfront_origin_access_control.cfb_data.id
#   }]
#
#   extra_behaviors = [{
#     path_pattern     = "/cfb/data/*"
#     target_origin_id = local.cfb_data_origin_id
#   }]
#
# CachingOptimized honours origin Cache-Control headers, so freshness is set
# at upload time by publish-data.sh rather than here.

# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------
# Reads the outputs of the existing modules/cloudfront. The distribution_arn
# output was added for these parameters -- the module previously exported
# only id, domain_name, and zone_id.

resource "aws_ssm_parameter" "cdn_distribution_id" {
  name        = "/travispollard/cdn/distribution_id"
  description = "CloudFront distribution serving travispollard.com"
  type        = "String"
  value       = module.cloudfront.cloudfront_distribution_id
}

resource "aws_ssm_parameter" "cdn_distribution_arn" {
  name        = "/travispollard/cdn/distribution_arn"
  description = "ARN of the CloudFront distribution serving travispollard.com"
  type        = "String"
  value       = module.cloudfront.cloudfront_distribution_arn
}
