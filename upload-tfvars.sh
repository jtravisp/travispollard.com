#!/bin/bash
set -euo pipefail

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
# Account 679878703800. Reads AWS_PROFILE so a shell that already exports one is
# believed, and falls back to the name this account is configured under. The
# previous hardcoded "tpollard" does not exist on this machine, and a profile
# that does not exist fails differently from one pointing at the wrong account:
# a similarly-named "jtravisp" resolves to 100611042748 and returns nothing.
PROFILE="${AWS_PROFILE:-tp-site}"
REGION="${AWS_REGION:-us-east-1}"

# See download-tfvars.sh. Git Bash rewrites "/projects/..." into a Windows path
# before aws.exe sees it, and on *this* script that is worse than a failed read:
# --overwrite would happily create a second parameter named after a directory on
# C:, leaving the real one stale while the run reports success.
export MSYS_NO_PATHCONV=1

if [ ! -s terraform.tfvars ]; then
  echo "terraform.tfvars is missing or empty -- refusing to overwrite $PARAM_NAME with it." >&2
  exit 1
fi

echo "Uploading terraform.tfvars to SSM at $PARAM_NAME..."

aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value "file://terraform.tfvars" \
  --type String \
  --overwrite \
  --profile "$PROFILE" \
  --region "$REGION"

echo "Upload complete!"
