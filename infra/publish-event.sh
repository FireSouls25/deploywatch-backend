#!/usr/bin/env bash
# Registra un despliegue: mensaje en SQS + reporte JSON en S3.
# Uso: infra/publish-event.sh <resultado> <sha> <imagen> [staging|production]
set -euo pipefail
cd "$(dirname "$0")"
RESULTADO=${1:?resultado}; SHA=${2:?sha}; IMAGEN=${3:?imagen}; ENTORNO=${4:-staging}

queue_url=$(./aws-local.sh sqs get-queue-url --queue-name "deploywatch-$ENTORNO-deploy-events" \
  --query QueueUrl --output text)
evento=$(printf '{"resultado":"%s","sha":"%s","imagen":"%s","entorno":"%s","fecha":"%s"}' \
  "$RESULTADO" "$SHA" "$IMAGEN" "$ENTORNO" "$(date -u +%FT%TZ)")

./aws-local.sh sqs send-message --queue-url "$queue_url" --message-body "$evento" >/dev/null
printf '%s' "$evento" | ./aws-local.sh s3 cp - "s3://deploywatch-$ENTORNO-deploy-reports/despliegues/$SHA.json" \
  --content-type application/json >/dev/null
echo "Evento registrado: $evento"
