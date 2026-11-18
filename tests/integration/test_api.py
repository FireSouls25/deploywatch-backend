"""API completa sobre SQLite real (archivo temporal) y un GitHub falso."""
import pytest
from fastapi.testclient import TestClient
from jsonschema import validate
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.domain.repo import RunInfo, WorkflowInfo
from app.infrastructure.db import (
    Base,
    SqlCheckRepository,
    SqlRepoRepository,
    ensure_provider_column,
    make_engine,
)
from app.main import app

# Contrato de GET /api/repos: lo que consume el frontend.
CHECK_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "outcome": {"type": "string"},
        "message": {"type": "string"},
        "workflow_name": {"type": ["string", "null"]},
        "run_url": {"type": ["string", "null"]},
        "checked_at": {"type": "string"},
        "needs_attention": {"type": "boolean"},
        "provider": {"type": ["string", "null"]},
    },
    "required": ["outcome", "message", "checked_at", "needs_attention", "provider"],
}
REPOS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "full_name": {"type": "string"},
            "url": {"type": "string"},
            "last_check": CHECK_SCHEMA,
        },
        "required": ["id", "full_name", "url", "last_check"],
    },
}


class FakeGithub:
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def list_workflows(self, repo):
        if self.fail:
            raise RuntimeError("rate limit")
        return [WorkflowInfo(workflow_id=1, name="deploy", path="deploy.yml")]

    async def list_runs(self, repo, workflow_name=None):
        return [RunInfo(name="deploy", status="completed", conclusion="failure",
                        html_url="http://run")]

    async def list_deployments(self, repo):
        return []

    async def list_environments(self, repo):
        return []

    async def list_external_checks(self, repo):
        return []


@pytest.fixture
def github():
    return FakeGithub()


@pytest.fixture
def client(monkeypatch, tmp_path, github):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    ensure_provider_column(engine)
    session = sessionmaker(bind=engine)
    repos, checks = SqlRepoRepository(session), SqlCheckRepository(session)

    monkeypatch.setattr(deps, "get_repo_repo", lambda: repos)
    monkeypatch.setattr(deps, "get_check_repo", lambda: checks)
    monkeypatch.setattr(deps, "get_github", lambda: github)
    return TestClient(app)


def _track(client, url="https://github.com/octo/repo"):
    return client.post("/api/repos", json={"url": url})


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_full_flow_track_check_list_delete(client):
    repo_id = _track(client).json()["id"]

    check = client.post(f"/api/repos/{repo_id}/check")
    listed = client.get("/api/repos")
    deleted = client.delete(f"/api/repos/{repo_id}")

    assert check.status_code == 200
    assert check.json()["last_check"]["outcome"] == "failure"
    assert check.json()["last_check"]["needs_attention"] is True
    validate(instance=listed.json(), schema=REPOS_SCHEMA)
    assert listed.json()[0]["full_name"] == "octo/repo"
    assert deleted.status_code == 204
    assert client.get("/api/repos").json() == []


def test_unchecked_repo_matches_contract(client):
    _track(client)

    listed = client.get("/api/repos").json()

    validate(instance=listed, schema=REPOS_SCHEMA)
    assert listed[0]["last_check"] is None


@pytest.mark.parametrize(
    "method, path, body, expected_status",
    [
        ("post", "/api/repos", {"url": "no-es-un-repo"}, 400),
        ("post", "/api/repos", {"url": "https://github.com/octo/repo"}, 409),
        ("post", "/api/repos", {}, 422),
        ("post", "/api/repos/no-existe/check", None, 404),
        ("delete", "/api/repos/no-existe", None, 404),
    ],
)
def test_error_responses(client, method, path, body, expected_status):
    _track(client)  # deja octo/repo registrado para provocar el 409

    response = client.request(method, path, json=body)

    assert response.status_code == expected_status


@pytest.mark.parametrize("github", [FakeGithub(fail=True)])
def test_github_failure_returns_502(client):
    repo_id = _track(client).json()["id"]

    response = client.post(f"/api/repos/{repo_id}/check")

    assert response.status_code == 502
