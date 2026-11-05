import pytest

from app.application import usecases
from app.domain.repo import RunInfo, WorkflowInfo
from app.infrastructure.memory import InMemoryChecks, InMemoryRepos


class FakeGithub:
    def __init__(self, workflows, runs):
        self._wf, self._runs = workflows, runs

    async def list_workflows(self, repo):
        return self._wf

    async def list_runs(self, repo, workflow_name=None):
        return self._runs


async def test_track_and_check_success():
    repos, checks = InMemoryRepos(), InMemoryChecks()
    tracked = await usecases.track_repo("https://github.com/octo/repo", repos)
    gh = FakeGithub(
        [WorkflowInfo(workflow_id=1, name="deploy", path="deploy.yml")],
        [RunInfo(name="d", status="completed", conclusion="success", html_url="http://x")],
    )
    check = await usecases.check_repo_now(tracked.id, repos, checks, gh)
    assert check.outcome.value == "success"


async def test_track_duplicate_raises():
    repos = InMemoryRepos()
    await usecases.track_repo("octo/repo", repos)
    with pytest.raises(usecases.RepoAlreadyTracked):
        await usecases.track_repo("https://github.com/octo/repo", repos)


async def test_check_unknown_repo_raises():
    with pytest.raises(usecases.RepoNotFound):
        await usecases.check_repo_now(
            "missing", InMemoryRepos(), InMemoryChecks(), FakeGithub([], [])
        )
