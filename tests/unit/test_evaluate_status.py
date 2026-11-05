from app.domain.repo import DeploymentInfo, DeployOutcome, EnvironmentInfo, RunInfo, WorkflowInfo
from app.domain.services import evaluate_deploy_status


def _wf(name="Deploy to prod"):
    return WorkflowInfo(workflow_id=1, name=name, path=".github/workflows/deploy.yml")


def _run(status="completed", conclusion="success"):
    return RunInfo(
        name="deploy", status=status, conclusion=conclusion,
        html_url="https://github.com/o/r/actions/runs/1",
    )


def test_no_deploy_workflow_needs_attention():
    s = evaluate_deploy_status(
        [WorkflowInfo(workflow_id=1, name="CI", path=".github/workflows/ci.yml")], [_run()]
    )
    assert s.outcome == DeployOutcome.NO_DEPLOY_SETUP
    assert s.needs_attention is True


def test_never_deployed_needs_attention():
    s = evaluate_deploy_status([_wf()], [])
    assert s.outcome == DeployOutcome.NEVER_DEPLOYED
    assert s.needs_attention is True


def test_success_no_attention():
    s = evaluate_deploy_status([_wf()], [_run(conclusion="success")])
    assert (s.outcome, s.needs_attention) == (DeployOutcome.SUCCESS, False)


def test_failure_needs_attention():
    s = evaluate_deploy_status([_wf()], [_run(conclusion="failure")])
    assert (s.outcome, s.needs_attention) == (DeployOutcome.FAILURE, True)


def test_in_progress_no_attention():
    s = evaluate_deploy_status([_wf()], [_run(status="in_progress", conclusion=None)])
    assert s.outcome == DeployOutcome.IN_PROGRESS


def _dep(state="success", env="production"):
    return DeploymentInfo(
        deployment_id=1, environment=env, state=state,
        target_url="https://app.example.com", created_at="2026-01-02T00:00:00Z",
    )


def test_external_deployment_counts_as_deploy_setup():
    """Un repo con Pages/Vercel/Cloudflare publica deployments aunque no
    tenga ningún workflow con 'deploy': ya no es NO_DEPLOY_SETUP."""
    s = evaluate_deploy_status(
        [WorkflowInfo(workflow_id=1, name="CI", path=".github/workflows/ci.yml")],
        [],
        deployments=[_dep("success")],
    )
    assert (s.outcome, s.needs_attention) == (DeployOutcome.SUCCESS, False)


def test_external_deployment_failure_needs_attention():
    s = evaluate_deploy_status([], [], deployments=[_dep("failure")])
    assert (s.outcome, s.needs_attention) == (DeployOutcome.FAILURE, True)


def test_latest_event_wins_over_older_workflow_run():
    s = evaluate_deploy_status(
        [_wf()],
        [_run(status="completed", conclusion="success")],
        deployments=[_dep("failure")],
    )
    assert s.outcome == DeployOutcome.FAILURE


def test_environments_without_activity_means_never_deployed():
    s = evaluate_deploy_status(
        [], [], environments=[EnvironmentInfo(name="github-pages")]
    )
    assert (s.outcome, s.needs_attention) == (
        DeployOutcome.NEVER_DEPLOYED, True,
    )


def test_unrelated_ci_runs_do_not_count_as_deploys():
    s = evaluate_deploy_status(
        [WorkflowInfo(workflow_id=1, name="CI", path=".github/workflows/ci.yml")],
        [_run(status="completed", conclusion="success")],
    )
    assert s.outcome == DeployOutcome.NO_DEPLOY_SETUP
