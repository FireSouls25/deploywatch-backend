#!/usr/bin/env bash
# AWS CLI apuntando SIEMPRE a LocalStack, con credenciales de prueba.
# Ignora cualquier perfil o credencial real de la máquina.
set -euo pipefail
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=${AWS_REGION:-us-east-1} AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1}
export AWS_ENDPOINT_URL=${LOCALSTACK_URL:-http://localhost:4566}
export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_PAGER=
unset AWS_PROFILE AWS_SESSION_TOKEN
exec aws "$@"
