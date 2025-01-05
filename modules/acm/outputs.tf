output "certificate_arn" {
  value = aws_acm_certificate.this.arn
}

output "validation_options" {
  value = aws_acm_certificate.this.domain_validation_options
}

output "validation_record_fqdns" {
  value = {
    for record in aws_route53_record.cert_validation : record.name => record.fqdn
  }
}
