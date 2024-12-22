module "route53" {
  source = "./modules/route53"

  zone_name              = var.zone_name
  mx_records             = var.mx_records
  ns_records             = var.ns_records
  soa_records            = var.soa_records
  acm_validation_records = var.acm_validation_records
  cloudfront_domain_name = var.cloudfront_domain_name
  cloudfront_zone_id     = var.cloudfront_zone_id
}


module "s3" {
  source = "./modules/s3" # Path to your S3 module

  bucket_name = "existing-bucket-name" # Replace with your bucket's name
  region      = "us-east-1"            # Replace with your bucket's region
}
