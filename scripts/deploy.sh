#!/usr/bin/env bash
# Despliegue a staging con smoke test y rollback automático.
#
# Uso: deploy.sh <imagen-nueva> [<imagen-estable>]
#
#   1. Levanta Postgres y la versión estable actual (si existe).
#   2. Reemplaza la API por la imagen nueva y ejecuta el smoke test.
#   3. Si el smoke test falla, vuelve a la versión estable (rollback)
#      y termina con código 1 para que el pipeline quede en rojo.
#
# SIMULAR_FALLO=true despliega la imagen nueva con una DATABASE_URL inválida
# para demostrar el rollback sin romper el código.
set -euo pipefail

NEW_IMAGE=${1:?Falta la imagen nueva}
STABLE_IMAGE=${2:-}
NET=deploywatch-staging
DB=staging-db
API=staging-api
HEALTH_URL=http://localhost:8000/api/health

PG_PASSWORD=$(openssl rand -hex 16)
DB_URL="postgresql+psycopg://deploywatch:${PG_PASSWORD}@${DB}:5432/deploywatch"
BROKEN_DB_URL="postgresql+psycopg://deploywatch@host-inexistente:5432/deploywatch"

log() { echo "::group::$*"; }
end() { echo "::endgroup::"; }

start_db() {
  log "Postgres de staging"
  docker network create "$NET" >/dev/null 2>&1 || true
  docker rm -f "$DB" >/dev/null 2>&1 || true
  docker run -d --name "$DB" --network "$NET" \
    -e POSTGRES_USER=deploywatch -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -e POSTGRES_DB=deploywatch postgres:16-alpine >/dev/null
  for _ in $(seq 1 30); do
    docker exec "$DB" pg_isready -U deploywatch >/dev/null 2>&1 && { end; return 0; }
    sleep 1
  done
  echo "Postgres no arrancó"; end; return 1
}

run_api() { # <imagen> <database-url>
  docker rm -f "$API" >/dev/null 2>&1 || true
  docker run -d --name "$API" --network "$NET" -p 8000:8000 \
    -e DATABASE_URL="$2" "$1" >/dev/null
}

smoke_test() {
  for _ in $(seq 1 15); do
    if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"ok"'; then
      echo "Smoke test OK: $HEALTH_URL"
      return 0
    fi
    sleep 2
  done
  echo "Smoke test FALLÓ: $HEALTH_URL no respondió {\"status\":\"ok\"}"
  docker logs --tail 20 "$API" 2>&1 || true
  return 1
}

start_db

if [[ -n "$STABLE_IMAGE" ]]; then
  log "Versión estable actual: $STABLE_IMAGE"
  run_api "$STABLE_IMAGE" "$DB_URL"
  if ! smoke_test; then
    echo "La versión estable no pasa el smoke test: no sirve como punto de rollback."
    STABLE_IMAGE=""
  fi
  end
fi

log "Desplegando versión nueva: $NEW_IMAGE"
url="$DB_URL"
[[ "${SIMULAR_FALLO:-false}" == "true" ]] && { echo "SIMULAR_FALLO=true"; url="$BROKEN_DB_URL"; }
run_api "$NEW_IMAGE" "$url"
if smoke_test; then
  end
  echo "resultado=desplegado" >> "${GITHUB_OUTPUT:-/dev/null}"
  exit 0
fi
end

if [[ -z "$STABLE_IMAGE" ]]; then
  echo "No hay versión estable a la que volver."
  echo "resultado=fallido" >> "${GITHUB_OUTPUT:-/dev/null}"
  exit 1
fi

log "ROLLBACK a $STABLE_IMAGE"
run_api "$STABLE_IMAGE" "$DB_URL"
smoke_test
end
echo "resultado=rollback" >> "${GITHUB_OUTPUT:-/dev/null}"
exit 1
