#!/usr/bin/env bash
# Demostración local del pipeline completo de DeployWatch (requiere Docker).
#
# Uso: scripts/demo-local.sh [paso]
#
#   pruebas     lint, pruebas y quality gate de cobertura (80 %)
#   despliegue  construye la imagen y la despliega en staging con smoke test
#   rollback    despliega una versión con configuración rota: rollback automático
#   carga       prueba de carga con Locust contra staging (quality gate p95 / errores)
#   iac         LocalStack + CloudFormation: cola SQS y bucket S3, publica y lee eventos
#   limpiar     elimina los contenedores de la demo
#   todo        todos los pasos anteriores en orden (por defecto)
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=.venv-demo
IMG=deploywatch-backend
PASO=${1:-todo}

titulo() { printf '\n\033[1;33m== %s ==\033[0m\n' "$*"; }

puerto_libre() {
  if docker ps --format '{{.Names}} {{.Ports}}' | grep -v '^staging-' | grep -q ':8000->'; then
    echo "El puerto 8000 está ocupado por otro contenedor. Deténlo antes de la demo:"
    docker ps --format '  {{.Names}} {{.Ports}}' | grep ':8000->'
    exit 1
  fi
}

entorno_python() {
  if [[ ! -x $VENV/bin/coverage ]]; then
    titulo "Preparando entorno Python ($VENV)"
    "$(command -v python3.12 || command -v python3)" -m venv "$VENV"
    "$VENV/bin/pip" install -q --only-binary ":all:" --require-hashes -r requirements-dev.txt
    "$VENV/bin/pip" install -q --only-binary ":all:" --require-hashes -r requirements-load.txt
  fi
}

pruebas() {
  entorno_python
  titulo "1. Lint (ruff)"
  "$VENV/bin/ruff" check app tests load
  titulo "2. Pruebas + quality gate de cobertura (80 %)"
  "$VENV/bin/coverage" run -m pytest -q
  "$VENV/bin/coverage" report --fail-under=80 | tail -1
}

imagenes() {
  titulo "Construyendo la imagen Docker"
  local log; log=$(mktemp)
  docker build -q -t "$IMG:nueva" . >/dev/null 2>"$log" || { cat "$log"; exit 1; }
  rm -f "$log"
  # La primera vez, la versión estable es la misma imagen.
  docker image inspect "$IMG:stable" >/dev/null 2>&1 || docker tag "$IMG:nueva" "$IMG:stable"
}

despliegue() {
  puerto_libre; imagenes
  titulo "3. Despliegue a staging con smoke test"
  ./scripts/deploy.sh "$IMG:nueva" "$IMG:stable" | grep -vE '::|INFO:'
  docker tag "$IMG:nueva" "$IMG:stable"
  echo "Promovida: $IMG:nueva ahora es $IMG:stable"
}

rollback() {
  puerto_libre; imagenes
  titulo "4. Despliegue con configuración rota: rollback automático"
  if SIMULAR_FALLO=true ./scripts/deploy.sh "$IMG:nueva" "$IMG:stable" | grep -vE '::|INFO:'; then
    echo "Inesperado: el despliegue roto pasó el smoke test"; exit 1
  fi
  echo "El script terminó con error (como en el CD) y staging sigue sirviendo:"
  echo "  imagen activa: $(docker inspect -f '{{.Config.Image}}' staging-api)"
  echo "  /api/health:   $(curl -s localhost:8000/api/health)"
}

carga() {
  entorno_python
  curl -fs localhost:8000/api/health >/dev/null || despliegue
  titulo "5. Prueba de carga con Locust (20 usuarios, 20 s)"
  "$VENV/bin/locust" -f load/locustfile.py --headless -u 20 -r 10 -t 20s \
    --host http://localhost:8000 --only-summary 2>&1 | grep -E "Aggregated|Quality gate"
}

iac() {
  titulo "6. Infraestructura como código (LocalStack + CloudFormation)"
  docker compose --profile infra up -d localstack >/dev/null 2>&1 \
    || POSTGRES_PASSWORD=demo docker compose --profile infra up -d localstack
  ./infra/apply.sh staging
  echo "Aplicar de nuevo no cambia nada (idempotencia):"
  ./infra/apply.sh staging 2>&1 | grep -iE "no changes|up to date" || true
  ./infra/publish-event.sh desplegado "demo-$(date +%s)" "$IMG:nueva"
  ./infra/read-events.sh staging
}

limpiar() {
  titulo "Limpiando contenedores de la demo"
  docker rm -f staging-api staging-db >/dev/null 2>&1 || true
  docker network rm deploywatch-staging >/dev/null 2>&1 || true
  docker compose --profile infra rm -sf localstack >/dev/null 2>&1 \
    || POSTGRES_PASSWORD=demo docker compose --profile infra rm -sf localstack >/dev/null 2>&1 || true
  echo "Listo."
}

case "$PASO" in
  pruebas|despliegue|rollback|carga|iac|limpiar) "$PASO" ;;
  todo) pruebas; despliegue; rollback; carga; iac; limpiar ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
