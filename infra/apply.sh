#!/usr/bin/env bash
# Aplica infra/stack.yml en LocalStack (idempotente: solo cambia lo que difiere).
# Uso: infra/apply.sh [staging|production]
set -euo pipefail
cd "$(dirname "$0")"
ENTORNO=${1:-staging}
STACK=deploywatch-$ENTORNO

for _ in $(seq 1 30); do
  curl -fs "${LOCALSTACK_URL:-http://localhost:4566}/_localstack/health" >/dev/null && break
  sleep 2
done

./aws-local.sh cloudformation deploy --stack-name "$STACK" \
  --template-file stack.yml --parameter-overrides "Entorno=$ENTORNO" \
  --no-fail-on-empty-changeset
./aws-local.sh cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs" --output table
