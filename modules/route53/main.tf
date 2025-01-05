# Manage Route 53 Zone
resource "aws_route53_zone" "zone" {
  name = var.zone_name
}

# MX Records
resource "aws_route53_record" "mx" {
  zone_id = aws_route53_zone.zone.id
  name    = var.zone_name
  type    = "MX"
  ttl     = 3600
  records = var.mx_records
}

# NS Records
resource "aws_route53_record" "ns" {
  zone_id = aws_route53_zone.zone.id
  name    = var.zone_name
  type    = "NS"
  ttl     = 172800
  records = var.ns_records
}

# SOA Records
resource "aws_route53_record" "soa" {
  zone_id = aws_route53_zone.zone.id
  name    = var.zone_name
  type    = "SOA"
  ttl     = 900
  records = var.soa_records
}

# CNAME Validation Records (excluding apex and www)
resource "aws_route53_record" "cname_acm_validation" {
  for_each = {
    for domain, validation_record in var.acm_validation_records :
    domain => validation_record
    if domain != var.zone_name && domain != "www.${var.zone_name}"
  }

  zone_id = aws_route53_zone.zone.id
  name    = each.key
  type    = "CNAME"
  ttl     = 300
  records = [each.value]
}

# A Records (Apex with CloudFront Alias)
resource "aws_route53_record" "a" {
  zone_id = aws_route53_zone.zone.id
  name    = var.zone_name
  type    = "A"

  alias {
    name                   = var.cloudfront_domain_name
    zone_id                = var.cloudfront_zone_id
    evaluate_target_health = false
  }
}

# A Records (www with CloudFront Alias)
resource "aws_route53_record" "a_www" {
  zone_id = aws_route53_zone.zone.id
  name    = "www.${var.zone_name}"
  type    = "A"

  alias {
    name                   = var.cloudfront_domain_name
    zone_id                = var.cloudfront_zone_id
    evaluate_target_health = false
  }
}
