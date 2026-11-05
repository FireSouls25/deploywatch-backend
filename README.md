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

Un repo «tiene despliegue» si algún workflow contiene `deploy` en nombre o ruta.

| Situación | `outcome` | `needs_attention` |
|---|---|---|
| Sin workflow de despliegue | `no_deploy_setup` | 🔔 sí |
| Con workflow pero sin ejecuciones | `never_deployed` | 🔔 sí |
| Última ejecución en curso | `in_progress` | no |
| Última ejecución exitosa | `success` | no |
| Última ejecución fallida | `failure` | 🔔 sí |

## Requisitos

- Python 3.12+
- PostgreSQL 16 (solo para despliegue; en local vale SQLite)
- `GITHUB_TOKEN` opcional (eleva el límite de la API de GitHub)

## Instalación y uso local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# salud: http://localhost:8000/api/health
```

Variables de entorno (`ver .env.example`):

| Variable | Defecto | Descripción |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./deploywatch.db` | Conexión SQLAlchemy (Postgres en Docker) |
| `GITHUB_TOKEN` | — | Token personal para la API de GitHub |
| `GITHUB_API` | `https://api.github.com` | Base de la API de GitHub |

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Salud del servicio |
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
- `tests/integration`: flujo HTTP con `TestClient` y gateway simulado.
- CI (`.github/workflows/ci.yml`): lint + tests con cobertura + build Docker.
- SonarCloud (`sonar-project.properties`): usa `coverage.xml` como reporte Python.

## Docker

```bash
cp .env.example .env   # opcional: define GITHUB_TOKEN
docker compose up --build
# api: http://localhost:8000/api/health
```

El `compose` levanta `db` (Postgres 16) + `api`. El frontend vive en su propio
repo y consume esta API por `/api`.
