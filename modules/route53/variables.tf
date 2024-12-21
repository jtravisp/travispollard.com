variable "zone_name" {
  description = "The domain name for the Route 53 zone"
  type        = string
}

variable "mx_records" {
  description = "MX records for email"
  type        = list(string)
}

variable "ns_records" {
  description = "NS records for the zone"
  type        = list(string)
}

variable "soa_records" {
  description = "SOA record for the zone"
  type        = list(string)
}

variable "acm_validation_records" {
  description = "CNAME records for ACM validation"
  type        = map(string)
}

variable "cloudfront_domain_name" {
  description = "Domain name for CloudFront distribution"
  type        = string
}

variable "cloudfront_zone_id" {
  description = "Hosted zone ID for the CloudFront distribution"
  type        = string
}
