# Cache-Control for the site, set at CloudFront.
#
# Why here and not on the objects: the deploy is a console-built CodePipeline
# S3 action, outside this Terraform, and it can stamp one Cache-Control value
# on every object in the artifact. One value cannot be both "a year,
# immutable" for hashed assets and "revalidate every time" for HTML. A
# response headers policy per cache behavior can, and it lives in code.
#
# Three tiers:
#
#   /_next/static/*  public, max-age=31536000, immutable
#                    Next.js content-hashes every file under here: a changed
#                    file gets a new name, so a cached copy can never be stale.
#
#   everything else  public, max-age=0, must-revalidate
#                    HTML, sitemap*.xml, robots.txt, images/og-card.png, the
#                    resume PDF. None are content-hashed, and a deploy must be
#                    visible on the next load. Revalidation is a conditional
#                    GET answered 304 from the S3 ETag, so "no-cache" costs a
#                    round trip, not a download.
#
#   /cfb/data/*      untouched. Deliberately NOT immutable: those documents
#                    are republished in place under the same names. Their
#                    freshness is set at upload by the football pipeline
#                    (public, max-age=300, must-revalidate) and honoured by
#                    CachingOptimized -- see cfb-wiring.tf. No response headers
#                    policy is attached, so nothing here can override it.
#
# Edge caching is unchanged. The default behavior already uses
# Managed-CachingOptimized (658327ea-...), and with no Cache-Control from the
# S3 origin the edge keeps objects for that policy's default day -- which is
# why the pipeline invalidates after every deploy. A response headers policy
# changes only what the browser is told, not the edge TTL, so the invalidation
# stays necessary and stays sufficient. The new /_next/static/* behavior uses
# the same managed policy.

data "aws_cloudfront_cache_policy" "static_assets" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_response_headers_policy" "immutable" {
  name    = "travispollard-immutable-assets"
  comment = "Content-hashed /_next/static/* assets"

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "public, max-age=31536000, immutable"
      override = true
    }
  }
}

resource "aws_cloudfront_response_headers_policy" "revalidate" {
  name    = "travispollard-revalidate"
  comment = "HTML and every other un-hashed file: revalidate on each load"

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "public, max-age=0, must-revalidate"
      override = true
    }
  }
}

locals {
  static_asset_behaviors = [{
    path_pattern               = "/_next/static/*"
    target_origin_id           = "${module.s3.bucket_name}.s3-website-us-east-1.amazonaws.com"
    cache_policy_id            = data.aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.immutable.id
  }]
}
