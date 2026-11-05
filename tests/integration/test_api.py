from fastapi.testclient import TestClient

from app.api import deps, routes
from app.domain.repo import RunInfo, WorkflowInfo
from app.infrastructure.memory import InMemoryChecks, InMemoryRepos


class FakeGithub:
    async def list_workflows(self, repo):
        return [WorkflowInfo(workflow_id=1, name="deploy", path="deploy.yml")]

    async def list_runs(self, repo, workflow_name=None):
        return [
            RunInfo(name="d", status="completed", conclusion="failure",
                    html_url="http://run")
        ]

    async def list_deployments(self, repo):
        return []

    async def list_environments(self, repo):
        return []


def _client():
    repos, checks = InMemoryRepos(), InMemoryChecks()
    deps.get_repo_repo = lambda: repos  # type: ignore
    deps.get_check_repo = lambda: checks  # type: ignore
    # routes imports getters lazily, but patch module attr used inside funcs
    import importlib

    importlib.reload(routes)
    from app.main import app

    return TestClient(app)


def test_api_flow():
    c = _client()
    assert c.get("/api/health").json() == {"status": "ok"}

    r = c.post("/api/repos", json={"url": "https://github.com/octo/repo"})
    assert r.status_code == 201, r.text
    repo_id = r.json()["id"]

    # override gateway used by route
    deps.get_github = lambda: FakeGithub()  # type: ignore
    import importlib

    importlib.reload(routes)
    from app.main import app as app2

    c2 = TestClient(app2)
    chk = c2.post(f"/api/repos/{repo_id}/check")
    assert chk.status_code == 200, chk.text
    assert chk.json()["last_check"]["outcome"] == "failure"
    assert chk.json()["last_check"]["needs_attention"] is True
