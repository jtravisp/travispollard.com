module "route53" {
  source = "./modules/route53"

  zone_name              = var.zone_name
  mx_records             = var.mx_records
  ns_records             = var.ns_records
  soa_records            = var.soa_records

 acm_validation_records = {
    for dvo in module.acm.validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      value = dvo.resource_record_value
    }
  }

  cloudfront_domain_name = module.cloudfront.cloudfront_domain_name
  cloudfront_zone_id     = module.cloudfront.cloudfront_zone_id
}


module "s3" {
  source                  = "./modules/s3"
  bucket_name             = var.zone_name
  region                  = var.region
  cloudfront_distribution_id = module.cloudfront.cloudfront_distribution_id
}

module "acm" {
  source = "./modules/acm"

  domain_name = var.zone_name
  subject_alternative_names = var.subject_alternative_names
  zone_id     = module.route53.zone_id
}

module "cloudfront" {
  source = "./modules/cloudfront"

  default_root_object = "index.html"
  origin_domain_name  = "${module.s3.bucket_name}.s3-website-us-east-1.amazonaws.com"
  origin_id           = "${module.s3.bucket_name}.s3-website-us-east-1.amazonaws.com"
  acm_certificate_arn     = module.acm.certificate_arn
}
