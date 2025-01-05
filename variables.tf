variable "zone_name" {
  description = "The domain name for the Route 53 zone"
  type        = string
}

variable "mx_records" {
  description = "The MX records for the domain"
  type        = list(string)
}

variable "ns_records" {
  description = "The NS records for the domain"
  type        = list(string)
}

variable "soa_records" {
  description = "The SOA record for the domain"
  type        = list(string)
}

variable "subject_alternative_names" {
  type        = list(string)
}