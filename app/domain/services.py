"""Domain service: pure function mapping GitHub data -> DeployStatus."""
from __future__ import annotations

from .repo import DeployOutcome, DeployStatus, RunInfo, WorkflowInfo


def evaluate_deploy_status(
    workflows: list[WorkflowInfo], runs: list[RunInfo]
) -> DeployStatus:
    deploy_workflows = [w for w in workflows if w.looks_like_deploy()]
    if not deploy_workflows:
        return DeployStatus(
            outcome=DeployOutcome.NO_DEPLOY_SETUP,
            message="No workflow with 'deploy' in name/path found.",
            needs_attention=True,
        )

    primary = deploy_workflows[0]
    relevant = [r for r in runs] or []
    if not relevant:
        return DeployStatus(
            outcome=DeployOutcome.NEVER_DEPLOYED,
            message=f"Deploy workflow '{primary.name}' exists but never ran.",
            needs_attention=True,
            workflow_name=primary.name,
        )

    latest = relevant[0]
    if latest.status != "completed":
        return DeployStatus(
            outcome=DeployOutcome.IN_PROGRESS,
            message=f"Deploy '{primary.name}' is {latest.status}.",
            needs_attention=False,
            workflow_name=primary.name,
            run_url=latest.html_url,
        )
    if latest.conclusion == "success":
        return DeployStatus(
            outcome=DeployOutcome.SUCCESS,
            message=f"Last deploy '{primary.name}' succeeded.",
            needs_attention=False,
            workflow_name=primary.name,
            run_url=latest.html_url,
        )
    return DeployStatus(
        outcome=DeployOutcome.FAILURE,
        message=f"Last deploy '{primary.name}' {latest.conclusion or 'failed'}.",
        needs_attention=True,
        workflow_name=primary.name,
        run_url=latest.html_url,
    )
