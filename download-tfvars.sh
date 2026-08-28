#!/bin/bash

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
PROFILE="tp-site"   # account 679878703800; see cfb/docs/SPEC-phase0.md 5.5

echo "Downloading terraform.tfvars from SSM..."

aws ssm get-parameter \
  --name "$PARAM_NAME" \
  --query "Parameter.Value" \
  --output text \
  --profile "$PROFILE" > terraform.tfvars

echo "Download complete!"
