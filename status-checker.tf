# The /status page's data source: a Lambda on a ten-minute schedule that checks
# each project and writes status.json into this stack's site bucket.
#
# In the root stack rather than its own state because what it touches is this
# stack's: it writes one object into module.s3's bucket, and the page that reads
# it is served by module.cloudfront. A separate state would need an SSM seam to
# learn a bucket name this file can simply reference.
#
# Cost: 4,320 invocations a month of a few seconds at 128 MB, inside the Lambda
# free tier; one PutObject every ten minutes; logs kept 14 days.
#
# The object is served by the distribution's default behavior. The Lambda sets
# Cache-Control: public, max-age=60 on it, which that behavior's
# CachingOptimized policy honours -- without it the edge would keep the file for
# a day. The browser is told to revalidate by the response headers policy in
# cache-control.tf, like every other un-hashed file.
#
# The deploy pipeline copies the static export into the same bucket. It does
# not delete objects it did not ship, and the export deliberately contains no
# status.json, so a release never overwrites the checker's results.

locals {
  status_checker_name = "travispollard-status-checker"

  # What /status monitors. The ids are the ones content/projects.ts uses.
  status_targets = [
    { id = "near-mint-radar", name = "Near Mint Radar", url = "https://nearmintradar.com" },
    { id = "ncoer-writer", name = "NCOER Writer", url = "https://ncoer.travispollard.com" },
    { id = "cfb-forecast", name = "CFB Forecast", url = "https://travispollard.com/cfb" },
    { id = "lone-star-ampa", name = "Lone Star AMPA", url = "https://lonestarampa.com" },
  ]

  status_object_key = "status.json"
}

data "archive_file" "status_checker" {
  type        = "zip"
  source_file = "${path.module}/status-checker/checker.py"
  output_path = "${path.module}/.build/status-checker.zip"
}

# --- identity -----------------------------------------------------------------

data "aws_iam_policy_document" "status_checker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "status_checker" {
  name               = local.status_checker_name
  assume_role_policy = data.aws_iam_policy_document.status_checker_assume.json
}

# Least privilege: one object in one bucket, and its own log group. No
# s3:GetObject, no s3:ListBucket, no wildcard key -- a bug in the checker can
# overwrite status.json and nothing else on the site.
data "aws_iam_policy_document" "status_checker" {
  statement {
    sid       = "WriteStatusDocument"
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${module.s3.bucket_name}/${local.status_object_key}"]
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.status_checker.arn}:*"]
  }
}

resource "aws_iam_role_policy" "status_checker" {
  name   = "write-status-json"
  role   = aws_iam_role.status_checker.id
  policy = data.aws_iam_policy_document.status_checker.json
}

# Created here rather than on first invocation, so it has a retention period
# instead of keeping logs forever.
resource "aws_cloudwatch_log_group" "status_checker" {
  name              = "/aws/lambda/${local.status_checker_name}"
  retention_in_days = 14
}

# --- the function -------------------------------------------------------------

resource "aws_lambda_function" "status_checker" {
  function_name    = local.status_checker_name
  description      = "Synthetic checks for /status: availability, latency, TLS expiry."
  role             = aws_iam_role.status_checker.arn
  runtime          = "python3.12"
  handler          = "checker.handler"
  architectures    = ["arm64"]
  filename         = data.archive_file.status_checker.output_path
  source_code_hash = data.archive_file.status_checker.output_base64sha256

  memory_size = 128
  # Targets run concurrently with a 10 s timeout each, plus a TLS read; 60 s
  # leaves room for every one of them to time out and the write to still land.
  timeout = 60

  environment {
    variables = {
      TARGETS   = jsonencode(local.status_targets)
      BUCKET    = module.s3.bucket_name
      KEY       = local.status_object_key
      TIMEOUT_S = "10"
    }
  }

  depends_on = [
    aws_iam_role_policy.status_checker,
    aws_cloudwatch_log_group.status_checker,
  ]
}

# --- the schedule -------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "status_checker" {
  name                = local.status_checker_name
  description         = "Runs the /status checker."
  schedule_expression = "rate(10 minutes)"
}

resource "aws_cloudwatch_event_target" "status_checker" {
  rule = aws_cloudwatch_event_rule.status_checker.name
  arn  = aws_lambda_function.status_checker.arn
}

resource "aws_lambda_permission" "status_checker_events" {
  statement_id  = "AllowEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.status_checker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.status_checker.arn
}
