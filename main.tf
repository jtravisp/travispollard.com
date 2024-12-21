module "route53" {
  source = "./modules/route53"

  zone_name               = "travispollard.com"
  mx_records              = ["1 ASPMX.L.GOOGLE.COM.", "5 ALT1.ASPMX.L.GOOGLE.COM.", "5 ALT2.ASPMX.L.GOOGLE.COM.", "10 ALT3.ASPMX.L.GOOGLE.COM.", "10 ALT4.ASPMX.L.GOOGLE.COM."]
  ns_records              = ["ns-851.awsdns-42.net.", "ns-508.awsdns-63.com.", "ns-1098.awsdns-09.org.", "ns-1904.awsdns-46.co.uk."]
  soa_records             = ["ns-851.awsdns-42.net. awsdns-hostmaster.amazon.com. 1 7200 900 1209600 86400"]
  acm_validation_records  = {
    "_8fdbcf2b0bba69fe7492ca0b12715c73.travispollard.com." = "_23fa11eaaab161fedcab5e2ee1e04553.ghcgkbmxjw.acm-validations.aws."
    "_749fc501ec7b72619edcb2401e5f79ff.www.travispollard.com." = "_6365829f25d8d352925eaf110ce202b8.ghcgkbmxjw.acm-validations.aws."
  }
  cloudfront_domain_name  = "d3lnw7woce6vm9.cloudfront.net."
  cloudfront_zone_id      = "Z0634909Z5QHPV3Q53RZ"
}
