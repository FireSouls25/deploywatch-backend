#!/usr/bin/env bash
# Muestra los eventos de despliegue en cola y los reportes guardados en S3.
# Uso: infra/read-events.sh [staging|production]
set -euo pipefail
cd "$(dirname "$0")"
ENTORNO=${1:-staging}
queue_url=$(./aws-local.sh sqs get-queue-url --queue-name "deploywatch-$ENTORNO-deploy-events" \
  --query QueueUrl --output text)
echo "== Cola deploywatch-$ENTORNO-deploy-events"
./aws-local.sh sqs receive-message --queue-url "$queue_url" --max-number-of-messages 10 \
  --visibility-timeout 0 --query "Messages[].Body" --output text
echo "== Bucket deploywatch-$ENTORNO-deploy-reports"
./aws-local.sh s3 ls "s3://deploywatch-$ENTORNO-deploy-reports/despliegues/"
