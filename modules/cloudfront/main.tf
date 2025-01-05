resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = var.default_root_object

  origin {
    connection_attempts      = 3
    connection_timeout       = 10
    domain_name = var.origin_domain_name
    origin_id   = var.origin_id
    custom_origin_config {
        http_port                = 80
        https_port               = 443
        origin_keepalive_timeout = 5
        origin_protocol_policy   = "http-only" 
        origin_read_timeout      = 30
        origin_ssl_protocols     = ["TLSv1.2"]
        }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = var.origin_id
    cache_policy_id  = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    compress         = true

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn            = var.acm_certificate_arn
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }

    aliases         = ["travispollard.com", "www.travispollard.com"]
    price_class     = "PriceClass_100"
}
