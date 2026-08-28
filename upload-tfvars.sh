#!/bin/bash

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
# Account 679878703800. Reads AWS_PROFILE so a shell that already exports one is
# believed, and falls back to the name this account is configured under. The
# previous hardcoded "tpollard" does not exist on this machine, and a profile
# that does not exist fails differently from one pointing at the wrong account:
# a similarly-named "jtravisp" resolves to 100611042748 and returns nothing.
PROFILE="${AWS_PROFILE:-tp-site}"

echo "Uploading terraform.tfvars to SSM at $PARAM_NAME..."

aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value file://terraform.tfvars \
  --type String \
  --overwrite \
  --profile "$PROFILE"

echo "Upload complete!"
