#!/usr/bin/env bash
# Publish generated football JSON and invalidate the CDN.
#
# This script writes DATA ONLY. It does not deploy the website, does not
# touch the site bucket, and cannot trigger a site build. The Next.js routes
# under frontend/app/cfb/ fetch these files at runtime.
#
# Cache-Control is set here rather than in the CloudFront cache policy,
# because this script knows the publish cadence and the policy does not.

set -euo pipefail

BUCKET="${CFB_DATA_BUCKET:-travispollard-cfb-data}"
OUT_DIR="${OUT_DIR:-./out/data}"

if [[ ! -d "${OUT_DIR}" ]]; then
  echo "No generated data at ${OUT_DIR}" >&2
  exit 1
fi

DIST_ID="$(aws ssm get-parameter \
  --name /travispollard/cdn/distribution_id \
  --query 'Parameter.Value' --output text)"

# Five minutes as a safety net if invalidation fails. Predictions change
# weekly, so this is generous.
aws s3 sync "${OUT_DIR}" "s3://${BUCKET}/cfb/data/" \
  --delete \
  --content-type "application/json" \
  --cache-control "public, max-age=300, must-revalidate"

# One path, well inside the 1,000 free invalidation paths per month.
aws cloudfront create-invalidation \
  --distribution-id "${DIST_ID}" \
  --paths "/cfb/data/*" \
  --query 'Invalidation.Id' --output text
  