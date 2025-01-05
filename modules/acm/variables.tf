variable "domain_name" {
  description = "The domain name for the ACM certificate"
  type        = string
}

variable "subject_alternative_names" {
  description = "A list of additional domain names (SANs) for the ACM certificate"
  type        = list(string)
  default     = []
}

variable "zone_id" {
  description = "The Route 53 hosted zone ID"
  type        = string
}
