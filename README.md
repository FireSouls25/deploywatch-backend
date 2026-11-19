# DeployWatch · Backend

API que registra repositorios públicos de GitHub (por URL) y verifica bajo demanda
si tienen infraestructura de despliegue y si el último despliegue fue exitoso.
La alerta es dentro de la aplicación: el `last_check` devuelve `needs_attention`.

> Repositorio hermano: `deploywatch-frontend` (dashboard web).

## Arquitectura por dominios

```
app/
├── domain/          # Núcleo puro, sin E/S ni frameworks
│   ├── repo.py      # Entidades: TrackedRepo, DeployCheck; objetos de valor:
│   │                # GithubRepoId, DeployStatus; enum DeployOutcome
│   ├── services.py  # evaluate_deploy_status(workflows, runs) -> DeployStatus
│   └── ports.py     # Puertos: GithubGateway, RepoRepository, CheckRepository
├── application/     # Casos de uso: track_repo, list_repos_with_status, check_repo_now
├── infrastructure/  # Adaptadores: GithubApiAdapter (httpx), SQLAlchemy, fakes en memoria
└── api/             # FastAPI fino: rutas + deps.py (composition root)
```

### Regla de dominio

Un repo «tiene despliegue» si cumple alguna de estas cuatro señales:

1. Algún workflow contiene `deploy` en nombre o ruta.
2. La API de Deployments registra despliegues (aquí publican Vercel o Netlify
   cuando su integración de GitHub está conectada).
3. Statuses o checks externos en el HEAD de la rama por defecto
   (`Cloudflare Pages`, `pages-build-deployment`, `Vercel`...). Cubre el caso
   de plataformas que despliegan desde su propio panel, sin Actions en el
   repo y sin crear Deployments.
4. El repo tiene environments configurados (p. ej. `github-pages`).

Solo cuentan las ejecuciones cuyo workflow parece de despliegue: un CI en verde
no hace pasar por desplegado a un repo que jamás desplegó. Entre deployments
y ejecuciones manda el evento más reciente; después entran los checks
externos y, en último lugar, la infraestructura sin actividad.

Cada chequeo devuelve además `provider`: `cloudflare` | `vercel` |
`netlify` | `github-actions` | `github-pages` | `external` | `none`
(sin despliegue). Se deduce de nombres de workflows, checks y URLs, y se
guarda en la tabla `deploy_checks` (las BD anteriores se migran solas al
arrancar).

| Situación | `outcome` | `needs_attention` |
|---|---|---|
| Sin ninguna señal | `no_deploy_setup` | 🔔 sí |
| Infraestructura existente sin actividad | `never_deployed` | 🔔 sí |
| Último despliegue en curso | `in_progress` | no |
| Último despliegue exitoso | `success` | no |
| Último despliegue fallido | `failure` | 🔔 sí |

## Requisitos

- Python 3.12+
- PostgreSQL 16 (solo para despliegue; en local vale SQLite)
- `GITHUB_TOKEN` opcional (eleva el límite de la API de GitHub)

## Instalación y uso local

```bash
pip install -r requirements-dev.txt   # app + pytest, coverage, ruff
uvicorn app.main:app --reload --port 8000
# salud: http://localhost:8000/api/health
```

Variables de entorno (`ver .env.example`):

| Variable | Defecto | Descripción |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./deploywatch.db` | Conexión SQLAlchemy (Postgres en Docker) |
| `GITHUB_TOKEN` | — | Token personal para la API de GitHub |
| `GITHUB_API` | `https://api.github.com` | Base de la API de GitHub |
| `POSTGRES_PASSWORD` | — (obligatoria en compose) | Contraseña de Postgres; solo en `.env` |
| `POSTGRES_USER` / `POSTGRES_DB` | `deploywatch` | Usuario y base de Postgres |

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Salud del servicio y de la base de datos (503 si no responde) |
| `POST` | `/api/repos` `{url}` | Rastrear `owner/repo` o URL completa |
| `GET` | `/api/repos` | Listar con su último chequeo |
| `POST` | `/api/repos/{id}/check` | Verificación bajo demanda contra GitHub |
| `DELETE` | `/api/repos/{id}` | Dejar de rastrear |

## Pruebas y calidad

```bash
ruff check app tests
coverage run -m pytest -q && coverage report
```

- `tests/unit`: dominio (`GithubRepoId`, `evaluate_deploy_status`) y casos de uso con fakes en memoria.
- `tests/integration`: flujo HTTP con `TestClient` sobre SQLite temporal, contrato
  JSON Schema de `GET /api/repos` y respuestas de error parametrizadas.
- CI (`.github/workflows/ci.yml`): lint → tests → **quality gate de cobertura (80 %)**
  → reporte HTML como artifact → SonarCloud → build Docker. Acciones fijadas por SHA.
- SonarCloud (`sonar-project.properties`): usa `coverage.xml` y el reporte JUnit `test-results.xml`. Requiere el secreto
  `SONAR_TOKEN` y tener desactivado *Automatic Analysis* en SonarCloud.

## Dependencias

Las versiones están fijadas. Se editan los `.in` y se regeneran los `.txt`:

```bash
uv pip compile --generate-hashes --python-version 3.12 --python-platform linux requirements.in -o requirements.txt
uv pip compile --generate-hashes --python-version 3.12 --python-platform linux requirements-dev.in -o requirements-dev.txt
```

La imagen Docker instala solo `requirements.txt`, únicamente wheels y
corre con un usuario sin privilegios.

## Docker

```bash
cp .env.example .env   # define POSTGRES_PASSWORD (y opcionalmente GITHUB_TOKEN)
docker compose up --build
# api: http://localhost:8000/api/health
```

El `compose` levanta `db` (Postgres 16) + `api`; la API espera a que la base
pase su healthcheck. Ninguna credencial vive en el repositorio. El frontend vive en su propio
repo y consume esta API por `/api`.

## Prueba de carga (Locust)

`load/locustfile.py` simula usuarios con el panel abierto: registran un repo, consultan
`GET /api/repos` y `GET /api/health`, y lo eliminan al salir. Al terminar aplica un
**quality gate**: falla si la tasa de error supera el 1 % o el p95 supera 500 ms
(`LOAD_MAX_FAIL_RATIO`, `LOAD_MAX_P95_MS`). En el CI corre el job `load` contra la API
real sobre Postgres y publica el reporte HTML como artifact.

```bash
python -m venv .venv-load
.venv-load/bin/pip install --only-binary ":all:" --require-hashes -r requirements-load.txt
.venv-load/bin/locust -f load/locustfile.py --headless -u 30 -r 10 -t 45s \
  --host http://localhost:8000
```

## Demo local de todo el pipeline

`scripts/demo.py` reproduce en local, con Docker, cada etapa del pipeline. Es Python
puro, así que funciona igual en Linux, macOS y Windows (con Docker Desktop); en Windows
usa `py` o `python` en lugar de `python3`.

```bash
python3 scripts/demo.py             # todo, en orden (~2 min)
python3 scripts/demo.py pruebas     # lint, pruebas y gate de cobertura
python3 scripts/demo.py despliegue  # imagen, staging, smoke test y promoción
python3 scripts/demo.py rollback    # configuración rota: rollback automático
python3 scripts/demo.py carga       # Locust contra staging; deja locust-report.html
python3 scripts/demo.py iac         # LocalStack: aplicar plantilla, publicar y leer eventos
python3 scripts/demo.py limpiar
```

La primera vez crea `.venv-demo` con las dependencias fijadas por hash. Necesita libres
los puertos 8000 (staging) y 4566 (LocalStack). Los lockfiles son universales: incluyen
los paquetes y las huellas de Linux, macOS y Windows.

## Despliegue continuo (CD)

`.github/workflows/cd.yml` corre cuando el CI de `main` termina en verde:

1. Construye la imagen y la publica en GHCR con el SHA del commit como etiqueta.
2. `scripts/deploy.py` levanta staging (Postgres + API) con la versión `:stable`
   actual y la reemplaza por la nueva.
3. **Smoke test** sobre `GET /api/health`. Si falla, **rollback** automático a
   `:stable` y el pipeline queda en rojo. Si pasa, la imagen nueva se promueve a `:stable`.
4. Si existen los secretos `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`, avisa por Telegram.

Para demostrar el rollback: *Actions → cd → Run workflow* con `simular_fallo` marcado
(despliega la versión nueva con una `DATABASE_URL` inválida). En local:
`python3 scripts/deploy.py <imagen-nueva> <imagen-estable> --simular-fallo`.

## Infraestructura como código (LocalStack)

`infra/stack.yml` es una plantilla de **CloudFormation** que declara la infraestructura de
eventos de despliegue:

- Cola SQS `deploywatch-<entorno>-deploy-events` con su cola de mensajes fallidos (DLQ, 3 reintentos).
- Bucket S3 `deploywatch-<entorno>-deploy-reports`, versionado, cifrado y sin acceso público.

Se aplica contra **LocalStack** (emulador de AWS); el CD la levanta como servicio, aplica
la plantilla y registra cada despliegue (`desplegado`, `rollback` o `fallido`) como mensaje
en SQS y como reporte JSON en S3.

```bash
docker compose --profile infra up -d localstack
pip install --only-binary ":all:" --require-hashes -r requirements-infra.txt
python3 infra/localstack.py aplicar staging     # idempotente: solo aplica diferencias
python3 infra/localstack.py publicar desplegado <sha> <imagen>
python3 infra/localstack.py leer staging
```

`infra/localstack.py` fuerza credenciales de prueba y el endpoint de LocalStack, así que
nunca toca una cuenta real. LocalStack está fijado en 4.14: las versiones posteriores
exigen `LOCALSTACK_AUTH_TOKEN`.
