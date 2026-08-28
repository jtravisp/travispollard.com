# cfb/terraform — the football project's own state.
#
# Owns: the data bucket and the CI role that writes to it.
# Does not own: the domain, the cert, the distribution, or the site bucket.
#
# First apply order is root, then this. After that they are independent.

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Matched to the root stack rather than taking the newest provider. The
      # two roots disagree on real syntax across the v5/v6 line -- v6 deprecates
      # data.aws_region.current.name, which cfb-wiring.tf uses at the root -- and
      # one provider version across the repo is one thing to reason about.
      version = "~> 5.0"
    }
  }

  # Same bucket as the root stack, different key: separate state, separate
  # lifecycle. Neither root ever reads the other's remote state; the only seam
  # is the SSM parameters under /travispollard/cdn/.
  backend "s3" {
    bucket = "travispollard.com-tf-state"
    key    = "cfb/terraform.tfstate"
    region = "us-west-2"
  }
}

variable "cfb_data_bucket_name" {
  description = "Must match the value in the root stack."
  type        = string
  default     = "travispollard-cfb-data"
}

variable "region" {
  description = "Region the data bucket lives in. Scopes the SSM decrypt condition."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "owner/repo allowed to assume the publisher role"
  type        = string
  default     = "jtravisp/travispollard.com"
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "cdn_distribution_arn" {
  name = "/travispollard/cdn/distribution_arn"
}

# ---------------------------------------------------------------------------
# Data bucket
# ---------------------------------------------------------------------------
# Two prefixes with different purposes:
#   raw/       immutable source snapshots, never served, never overwritten
#   cfb/data/  generated JSON the site fetches
#
# Keys under cfb/data/ match the URL path exactly, so /cfb/data/latest.json
# maps to the key cfb/data/latest.json with no origin_path stripping.

resource "aws_s3_bucket" "cfb_data" {
  bucket = var.cfb_data_bucket_name
}

resource "aws_s3_bucket_public_access_block" "cfb_data" {
  bucket                  = aws_s3_bucket.cfb_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "cfb_data" {
  bucket = aws_s3_bucket.cfb_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cfb_data" {
  bucket = aws_s3_bucket.cfb_data.id

  # Raw snapshots are the irreplaceable asset. Keep them forever, but move
  # them out of Standard once they stop being read.
  rule {
    id     = "raw-to-infrequent-access"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

# ---------------------------------------------------------------------------
# CloudFront read access, scoped to the served prefix only
# ---------------------------------------------------------------------------
# The CDN can read cfb/data/* and nothing else. Raw snapshots are not
# reachable from the internet even by accident.

data "aws_iam_policy_document" "cfb_data_bucket" {
  statement {
    sid    = "AllowCloudFrontReadPublishedData"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.cfb_data.arn}/cfb/data/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [data.aws_ssm_parameter.cdn_distribution_arn.value]
    }
  }
}

resource "aws_s3_bucket_policy" "cfb_data" {
  bucket = aws_s3_bucket.cfb_data.id
  policy = data.aws_iam_policy_document.cfb_data_bucket.json
}

# ---------------------------------------------------------------------------
# Publisher role
# ---------------------------------------------------------------------------
# The pipeline runs on scheduled GitHub Actions. The site stays on CodeBuild.
# Different systems, so a football pipeline failure cannot affect a site
# deploy and vice versa.
#
# This role can write football data and invalidate football paths. It has no
# access to the site bucket at all.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "publisher_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to workflows in this repo. Tighten further with a specific
    # workflow ref if the repo gains untrusted contributors.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

data "aws_iam_policy_document" "publisher" {
  statement {
    sid       = "ListDataBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cfb_data.arn]
  }

  statement {
    sid       = "WriteRawSnapshots"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.cfb_data.arn}/raw/*"]
  }

  # Note: no s3:DeleteObject on raw/. Snapshots are immutable and the
  # pipeline has no business removing them.

  statement {
    sid       = "WritePublishedData"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.cfb_data.arn}/cfb/data/*"]
  }

  statement {
    sid       = "InvalidateOwnPaths"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [data.aws_ssm_parameter.cdn_distribution_arn.value]
  }

  statement {
    sid       = "ReadParameters"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/travispollard/*"]
  }

  # The CFBD API key is a SecureString. Decrypt is scoped by ViaService, so
  # this role can only use a key through SSM -- never to read anything else
  # the key happens to protect. Works with the default alias/aws/ssm key and
  # with a customer-managed key later, without an edit here.
  statement {
    sid       = "DecryptParametersViaSSM"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "publisher" {
  name               = "cfb-data-publisher"
  assume_role_policy = data.aws_iam_policy_document.publisher_trust.json
}

resource "aws_iam_role_policy" "publisher" {
  name   = "cfb-data-publisher"
  role   = aws_iam_role.publisher.id
  policy = data.aws_iam_policy_document.publisher.json
}

output "publisher_role_arn" {
  value = aws_iam_role.publisher.arn
}

output "data_bucket_name" {
  value = aws_s3_bucket.cfb_data.id
}
