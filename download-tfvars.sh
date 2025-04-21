#!/bin/bash

# SSM parameter path
PARAM_NAME="/projects/cloudresume/terraform/tfvars"
PROFILE="tpollard"

echo "Downloading terraform.tfvars from SSM..."

aws ssm get-parameter \
  --name "$PARAM_NAME" \
  --query "Parameter.Value" \
  --output text \
  --profile "$PROFILE" > terraform.tfvars

echo "Download complete!"
