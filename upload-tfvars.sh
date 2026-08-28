#!/bin/bash

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
PROFILE="tp-site"   # account 679878703800; see cfb/docs/SPEC-phase0.md 5.5

echo "Uploading terraform.tfvars to SSM at $PARAM_NAME..."

aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value file://terraform.tfvars \
  --type String \
  --overwrite \
  --profile "$PROFILE"

echo "Upload complete!"
