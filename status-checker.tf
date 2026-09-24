# The /status page's data source: a Lambda on a ten-minute schedule that checks
# each project and the site itself, keeps 30 days of daily counters in
# status-history.json, and writes status.json into this stack's site bucket.
#
# In the root stack rather than its own state because what it touches is this
# stack's: it writes one object into module.s3's bucket, and the page that reads
# it is served by module.cloudfront. A separate state would need an SSM seam to
# learn a bucket name this file can simply reference.
#
# Cost: 4,320 invocations a month of a few seconds at 512 MB, inside the Lambda
# free tier; one GetObject and two PutObjects every ten minutes (about $0.05 a
# month, the only line that is not free); logs kept 14 days. Old versions of
# both objects expire after a day (module.s3, expire_noncurrent_versions_of).
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

  # What /status monitors. The project ids are the ones content/projects.ts
  # uses; the site itself is checked at its canonical www host.
  status_targets = [
    { id = "travispollard-com", name = "travispollard.com", url = "https://www.travispollard.com" },
    { id = "near-mint-radar", name = "Near Mint Radar", url = "https://nearmintradar.com" },
    { id = "ncoer-writer", name = "NCOER Writer", url = "https://ncoer.travispollard.com" },
    { id = "cfb-forecast", name = "CFB Forecast", url = "https://travispollard.com/cfb" },
    { id = "lone-star-ampa", name = "Lone Star AMPA", url = "https://lonestarampa.com" },
  ]

  status_object_key  = "status.json"
  status_history_key = "status-history.json"
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

# Least privilege: two named objects in one bucket, and its own log group. No
# wildcard key -- a bug in the checker can overwrite status.json and its
# history and nothing else on the site.
data "aws_iam_policy_document" "status_checker" {
  statement {
    sid       = "WriteStatusDocument"
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${module.s3.bucket_name}/${local.status_object_key}"]
  }

  statement {
    sid       = "ReadWriteHistory"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::${module.s3.bucket_name}/${local.status_history_key}"]
  }

  # Without ListBucket, S3 answers a GetObject for a missing key with 403
  # rather than 404, and the checker could not tell "no history yet" from a
  # real permissions failure -- which it must, because on a failure it
  # refuses to overwrite the history. Scoped to that one key's prefix.
  statement {
    sid       = "TellMissingHistoryFromDenied"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${module.s3.bucket_name}"]
    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values   = [local.status_history_key]
    }
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

  # 512 MB, not 128: Lambda allocates CPU in proportion to memory, and at 128
  # MB the TLS handshakes were CPU-starved -- a cold run measured every site
  # over the 1 s threshold. The checker now times connection setup separately
  # as well, but a starved CPU still slows everything it does. Runs are
  # shorter at 512 MB, so the GB-seconds cost barely moves.
  memory_size = 512
  # Targets run concurrently with a 10 s connection timeout each; 60 s leaves
  # room for every one of them to time out and the writes to still land.
  timeout = 60

  environment {
    variables = {
      TARGETS     = jsonencode(local.status_targets)
      BUCKET      = module.s3.bucket_name
      KEY         = local.status_object_key
      HISTORY_KEY = local.status_history_key
      TIMEOUT_S   = "10"
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
