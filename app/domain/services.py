"""Domain service: pure function mapping GitHub data -> DeployStatus."""
from __future__ import annotations

from .repo import (
    DeploymentInfo,
    DeployOutcome,
    DeployStatus,
    EnvironmentInfo,
    RunInfo,
    WorkflowInfo,
)

_SUCCESS = {"success"}
_FAILURE = {"failure", "error"}
_ACTIVE_DEPLOYMENT = {"pending", "queued", "in_progress"}


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
    if state in _SUCCESS:
        return DeployStatus(
            outcome=DeployOutcome.SUCCESS,
            message=f"Último despliegue en '{dep.environment}' exitoso.",
            needs_attention=False,
            workflow_name=None,
            run_url=dep.target_url or None,
        )
    if state in _FAILURE:
        return DeployStatus(
            outcome=DeployOutcome.FAILURE,
            message=f"Último despliegue en '{dep.environment}' falló ({state}).",
            needs_attention=True,
            workflow_name=None,
            run_url=dep.target_url or None,
        )
    return DeployStatus(
        outcome=DeployOutcome.IN_PROGRESS,
        message=f"Despliegue en '{dep.environment}' en curso ({state}).",
        needs_attention=False,
        workflow_name=None,
        run_url=dep.target_url or None,
    )


def evaluate_deploy_status(
    workflows: list[WorkflowInfo],
    runs: list[RunInfo],
    deployments: list[DeploymentInfo] | None = None,
    environments: list[EnvironmentInfo] | None = None,
) -> DeployStatus:
    """Decide el estado de despliegue combinando tres señales.

    1. Deployments de GitHub (Cloudflare Pages, Vercel, Netlify...).
    2. Workflows con 'deploy' en nombre o ruta + sus ejecuciones.
    3. Environments configurados sin actividad todavía.
    """
    deployments = list(deployments or [])
    environments = list(environments or [])
    deploy_workflows = [w for w in workflows if w.looks_like_deploy()]

    if not deploy_workflows and not deployments and not environments:
        return DeployStatus(
            outcome=DeployOutcome.NO_DEPLOY_SETUP,
            message="Sin despliegue: no hay workflows de despliegue, "
            "deployments ni environments.",
            needs_attention=True,
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
        if latest_run.status != "completed":
            return DeployStatus(
                outcome=DeployOutcome.IN_PROGRESS,
                message=f"Despliegue '{primary.name}' {latest_run.status}.",
                needs_attention=False,
                workflow_name=primary.name,
                run_url=latest_run.html_url,
            )
        if latest_run.conclusion == "success":
            return DeployStatus(
                outcome=DeployOutcome.SUCCESS,
                message=f"Último despliegue '{primary.name}' exitoso.",
                needs_attention=False,
                workflow_name=primary.name,
                run_url=latest_run.html_url,
            )
        return DeployStatus(
            outcome=DeployOutcome.FAILURE,
            message=f"Último despliegue '{primary.name}' "
            f"{latest_run.conclusion or 'falló'}.",
            needs_attention=True,
            workflow_name=primary.name,
            run_url=latest_run.html_url,
        )

    # Hay infraestructura (workflow o environment) pero nunca se usó.
    origin = deploy_workflows[0].name if deploy_workflows else environments[0].name
    return DeployStatus(
        outcome=DeployOutcome.NEVER_DEPLOYED,
        message=f"'{origin}' existe pero nunca se ha desplegado.",
        needs_attention=True,
        workflow_name=deploy_workflows[0].name if deploy_workflows else None,
    )
