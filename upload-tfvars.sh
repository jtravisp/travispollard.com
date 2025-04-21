#!/bin/bash

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
PROFILE="tpollard"

echo "Uploading terraform.tfvars to SSM at $PARAM_NAME..."

aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value file://terraform.tfvars \
  --type String \
  --overwrite \
  --profile "$PROFILE"

echo "Upload complete!"
