"""Domain service: pure function mapping GitHub data -> DeployStatus."""
from __future__ import annotations

from .repo import (
    DeploymentInfo,
    DeployOutcome,
    DeployStatus,
    EnvironmentInfo,
    ExternalCheckInfo,
    RunInfo,
    WorkflowInfo,
)

_SUCCESS = {"success"}
_FAILURE = {"failure", "error"}
_ACTIVE_DEPLOYMENT = {"pending", "queued", "in_progress"}


def detect_provider(*texts: str | None) -> str:
    """Deduce la plataforma a partir de nombres y URLs.

    Devuelve cloudflare | vercel | netlify | github-pages |
    github-actions | external. El llamador decide 'none'.
    """
    blob = " ".join(t or "" for t in texts).lower()
    if (
        "cloudflare" in blob
        or "workers" in blob
        or "pages.dev" in blob
        or "dash.cloudflare" in blob
    ):
        return "cloudflare"
    if "vercel" in blob:
        return "vercel"
    if "netlify" in blob:
        return "netlify"
    if "pages-build-deployment" in blob or "github-pages" in blob:
        return "github-pages"
    if "github.com" in blob or "actions" in blob:
        return "github-actions"
    return "external"

# Palabras que delatan un estado/check de despliegue aunque no haya
# workflow propio: plataformas que despliegan desde su panel.
DEPLOY_KEYWORDS = (
    "deploy",
    "pages",
    "production",
    "preview",
    "cloudflare",
    "vercel",
    "netlify",
    "workers",
    "publish",
)


def _runs_of_deploy_workflows(
    deploy_workflows: list[WorkflowInfo], runs: list[RunInfo]
) -> list[RunInfo]:
    """Solo cuentan ejecuciones cuyo workflow parece de despliegue.

    Sin este filtro, una ejecución verde de CI haría pasar por
    desplegado un repo que jamás desplegó nada.
    """
    names = [w.name.lower() for w in deploy_workflows]
    return [
        r
        for r in runs
        if any(n in r.name.lower() or r.name.lower() in n for n in names)
    ]


def _map_deployment(dep: DeploymentInfo) -> DeployStatus:
    state = dep.state.lower()
    provider = detect_provider(dep.target_url, dep.environment)
    if state in _SUCCESS:
        return DeployStatus(
            outcome=DeployOutcome.SUCCESS,
            message=f"Último despliegue en '{dep.environment}' exitoso.",
            needs_attention=False,
            workflow_name=None,
            run_url=dep.target_url or None,
            provider=provider,
        )
    if state in _FAILURE:
        return DeployStatus(
            outcome=DeployOutcome.FAILURE,
            message=f"Último despliegue en '{dep.environment}' falló ({state}).",
            needs_attention=True,
            workflow_name=None,
            run_url=dep.target_url or None,
            provider=provider,
        )
    return DeployStatus(
        outcome=DeployOutcome.IN_PROGRESS,
        message=f"Despliegue en '{dep.environment}' en curso ({state}).",
        needs_attention=False,
        workflow_name=None,
        run_url=dep.target_url or None,
        provider=provider,
    )


def _map_external_check(check: ExternalCheckInfo) -> DeployStatus:
    state = check.state.lower()
    provider = detect_provider(check.name, check.url)
    if state in _SUCCESS:
        return DeployStatus(
            outcome=DeployOutcome.SUCCESS,
            message=f"Despliegue externo '{check.name}' exitoso.",
            needs_attention=False,
            workflow_name=None,
            run_url=check.url or None,
            provider=provider,
        )
    if state in _FAILURE:
        return DeployStatus(
            outcome=DeployOutcome.FAILURE,
            message=f"Despliegue externo '{check.name}' falló.",
            needs_attention=True,
            workflow_name=None,
            run_url=check.url or None,
            provider=provider,
        )
    return DeployStatus(
        outcome=DeployOutcome.IN_PROGRESS,
        message=f"Despliegue externo '{check.name}' en curso.",
        needs_attention=False,
        workflow_name=None,
        run_url=check.url or None,
        provider=provider,
    )


def evaluate_deploy_status(
    workflows: list[WorkflowInfo],
    runs: list[RunInfo],
    deployments: list[DeploymentInfo] | None = None,
    environments: list[EnvironmentInfo] | None = None,
    external_checks: list[ExternalCheckInfo] | None = None,
) -> DeployStatus:
    """Decide el estado de despliegue combinando cuatro señales.

    1. Deployments de GitHub (Cloudflare Pages, Vercel, Netlify...).
    2. Workflows con 'deploy' en nombre o ruta + sus ejecuciones.
    3. Statuses/checks externos en la rama por defecto (despliegues
       creados desde el panel de la plataforma, sin Actions propio).
    4. Environments configurados sin actividad todavía.
    Entre 1 y 2 manda el evento más reciente; 3 y 4 entran en ese orden.
    """
    deployments = list(deployments or [])
    environments = list(environments or [])
    deploy_checks = [
        c
        for c in (external_checks or [])
        if any(k in c.name.lower() for k in DEPLOY_KEYWORDS)
    ]
    deploy_workflows = [w for w in workflows if w.looks_like_deploy()]

    if (
        not deploy_workflows
        and not deployments
        and not environments
        and not deploy_checks
    ):
        return DeployStatus(
            outcome=DeployOutcome.NO_DEPLOY_SETUP,
            message="Sin despliegue: no hay workflows de despliegue, "
            "deployments, checks externos ni environments.",
            needs_attention=True,
            provider="none",
        )

    deploy_runs = _runs_of_deploy_workflows(deploy_workflows, runs)

    # El evento más reciente manda, sea de plataforma externa o de workflow.
    latest_dep = max(deployments, key=lambda d: d.created_at, default=None)
    latest_run = max(deploy_runs, key=lambda r: r.created_at, default=None)

    if latest_dep is not None and (
        latest_run is None or latest_dep.created_at >= latest_run.created_at
    ):
        return _map_deployment(latest_dep)

    if latest_run is not None:
        primary = deploy_workflows[0]
        provider = detect_provider(primary.name, primary.path, latest_run.html_url)
        if latest_run.status != "completed":
            return DeployStatus(
                outcome=DeployOutcome.IN_PROGRESS,
                message=f"Despliegue '{primary.name}' {latest_run.status}.",
                needs_attention=False,
                workflow_name=primary.name,
                run_url=latest_run.html_url,
                provider=provider,
            )
        if latest_run.conclusion == "success":
            return DeployStatus(
                outcome=DeployOutcome.SUCCESS,
                message=f"Último despliegue '{primary.name}' exitoso.",
                needs_attention=False,
                workflow_name=primary.name,
                run_url=latest_run.html_url,
                provider=provider,
            )
        return DeployStatus(
            outcome=DeployOutcome.FAILURE,
            message=f"Último despliegue '{primary.name}' "
            f"{latest_run.conclusion or 'falló'}.",
            needs_attention=True,
            workflow_name=primary.name,
            run_url=latest_run.html_url,
            provider=provider,
        )

    # Sin deployments ni ejecuciones: valen los checks externos (p. ej.
    # Cloudflare desplegando desde su panel) y, en último lugar,
    # la infraestructura configurada pero sin actividad.
    if deploy_checks:
        return _map_external_check(deploy_checks[0])

    # Hay infraestructura (workflow o environment) pero nunca se usó.
    origin = deploy_workflows[0].name if deploy_workflows else environments[0].name
    origin_path = deploy_workflows[0].path if deploy_workflows else ""
    return DeployStatus(
        outcome=DeployOutcome.NEVER_DEPLOYED,
        message=f"'{origin}' existe pero nunca se ha desplegado.",
        needs_attention=True,
        workflow_name=deploy_workflows[0].name if deploy_workflows else None,
        provider=detect_provider(origin, origin_path),
    )
