from app.domain.repo import DeployOutcome, RunInfo, WorkflowInfo
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
