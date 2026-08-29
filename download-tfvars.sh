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

# Git Bash rewrites any argument that looks like an absolute path into a Windows
# one before the process sees it, so "/projects/cloudresume/terraform/tfvars"
# arrives at aws.exe as "C:/Program Files/Git/projects/...". The call then fails
# with ParameterNotFound for a parameter that plainly exists -- which sends you
# looking at IAM and at the wrong-account trap above, neither of which is it.
export MSYS_NO_PATHCONV=1

# Region is explicit rather than inherited. Everything in this account is
# us-east-1 except the Terraform state bucket, and a shell whose profile has no
# region configured fails here rather than at plan time.

echo "Downloading terraform.tfvars from SSM..."

# Into a temp file first. The previous version redirected straight into
# terraform.tfvars, which bash truncates *before* running the command -- so a
# failed read left an empty tfvars behind and then printed "Download complete!".
# The next plan prompts for every variable, and the reason is two commands back.
TEMP="$(mktemp)"
trap 'rm -f "$TEMP"' EXIT

aws ssm get-parameter \
  --name "$PARAM_NAME" \
  --query "Parameter.Value" \
  --output text \
  --profile "$PROFILE" \
  --region "$REGION" > "$TEMP"

if [ ! -s "$TEMP" ]; then
  echo "Refusing to write an empty terraform.tfvars: $PARAM_NAME read back empty." >&2
  echo "Confirm the account first -- a similarly-named profile resolves elsewhere:" >&2
  echo "  aws sts get-caller-identity --profile $PROFILE --query Account --output text" >&2
  echo "  # expect 679878703800" >&2
  exit 1
fi

mv "$TEMP" terraform.tfvars
trap - EXIT
echo "Download complete! $(wc -c < terraform.tfvars) bytes."
