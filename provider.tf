terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    # Zips status-checker/checker.py for the status Lambda (status-checker.tf).
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket = "travispollard.com-tf-state"
    key    = "travispollard.com"
    region = "us-west-2"
  }
}

provider "aws" {
  region = var.region
}
