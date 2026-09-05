#!/usr/bin/env bash
# Tear down CampusAssist demo stack (run after presentation).
set -euo pipefail

STACK_NAME="${STACK_NAME:-campusassist}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

echo "Deleting SAM stack: $STACK_NAME ($REGION)"
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$REGION" || true
echo "Stack delete requested. Manually remove AgentCore Runtime agent / Managed KB if created outside SAM."
echo "Also empty+delete S3 buckets if retain policies applied."
