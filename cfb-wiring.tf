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
# Serving the published JSON
# ---------------------------------------------------------------------------
# Landed in Phase 1, as SPEC-phase0 section 10.2 said it would: Phase 0 applied
# only the two aws_ssm_parameter resources at the bottom of this file, because
# there was no JSON to serve and no reason to touch the live distribution.
# There is now -- `cfb publish` writes cfb/data/next-game.json and
# cfb/data/accuracy.json -- so the OAC and the behavior below are live.
#
# CachingOptimized rather than a TTL set here, and that is a deliberate split:
# it honours the origin's Cache-Control, so freshness is a property of the
# upload (`cfb.publish.CACHE_CONTROL`, SPEC-phase1 6.5) rather than of this
# file. One place decides how long a document is good for, and it is the place
# that knows what the document is.

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

locals {
  cfb_data_origin_id = "cfb-data-s3"

  # Referenced by convention rather than by data source or remote state, so
  # this stack has no dependency on cfb/terraform. CloudFront does not
  # validate the origin at create time.
  cfb_data_origin_domain = "${var.cfb_data_bucket_name}.s3.${data.aws_region.current.name}.amazonaws.com"
}

# The data bucket blocks all public access, so the CDN reaches it as a signed
# principal rather than over a website endpoint. cfb/terraform already holds the
# other half: a bucket policy allowing cloudfront.amazonaws.com to GetObject
# under cfb/data/* and nowhere else, conditioned on this distribution's ARN. So
# raw/ is unreachable from the internet even by accident, and it is unreachable
# because of a policy rather than because no behavior points at it.
resource "aws_cloudfront_origin_access_control" "cfb_data" {
  name                              = "cfb-data-oac"
  description                       = "OAC for the college football data bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ---------------------------------------------------------------------------
# Distribution changes
# ---------------------------------------------------------------------------
# modules/cloudfront is shared, so these go in as data and the module never
# learns the word "football". Both of its new variables default to empty, which
# is what makes this safe against a live distribution: passing nothing produces
# byte-identical config to what was there before.
#
# One deviation from the Phase 0 sketch, which proposed a single
# `extra_cache_policy_id` variable: the policy is carried per behavior instead.
# A shared module has no business assuming the next subpage wants the same
# caching as this one, and the two-line saving was not worth the assumption.
#
# Consumed by the `module "cloudfront"` block in main.tf. These live here rather
# than there so that everything football-shaped is in this one file, which is
# what makes it removable.

locals {
  cfb_extra_origins = [{
    origin_id   = local.cfb_data_origin_id
    domain_name = local.cfb_data_origin_domain
    oac_id      = aws_cloudfront_origin_access_control.cfb_data.id
  }]

  # /cfb/data/* only. The pages themselves are Next.js routes in the site
  # bucket and are served by the default behavior like every other route --
  # which is why this pattern is not /cfb/*, and why no CloudFront Function is
  # needed to rewrite directory indexes.
  cfb_extra_behaviors = [{
    path_pattern     = "/cfb/data/*"
    target_origin_id = local.cfb_data_origin_id
    cache_policy_id  = data.aws_cloudfront_cache_policy.optimized.id
  }]
}

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
