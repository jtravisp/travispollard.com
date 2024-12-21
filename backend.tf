terraform {
  backend "s3" {
    bucket                  = "travispollard.com-tf-state"
    key                     = "travispollard.com"
    region                  = "us-west-2"
    shared_credentials_files = ["~/.aws/credentials"]
  }
}
