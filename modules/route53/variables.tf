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
  description = "The ACM validation records (CNAMEs) required for domain validation"
  type = map(object({
    name  = string
    value = string
  }))
}

variable "cloudfront_domain_name" {
  description = "Domain name for CloudFront distribution"
  type        = string
}

variable "cloudfront_zone_id" {
  description = "Hosted zone ID for the CloudFront distribution"
  type        = string
}

variable "acm_validation_options" {
  description = "The validation options for the ACM certificate"
  type = list(object({
    domain_name           = string
    resource_record_name  = string
    resource_record_type  = string
    resource_record_value = string
  }))
  default = []
}
