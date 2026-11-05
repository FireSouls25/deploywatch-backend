"""Adapter-level: list_external_checks against a stubbed httpx client."""
import httpx
import pytest

from app.domain.repo import GithubRepoId
from app.infrastructure import github_adapter as adapter_mod
from app.infrastructure.github_adapter import (
    GithubApiAdapter,
    _normalize_check_run,
    _normalize_state,
)


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.is_success = 200 <= status < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.is_success:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore


class _FakeClient:
    def __init__(self, routes: dict):
        self._routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        for prefix, resp in self._routes.items():
            if url.startswith(prefix):
                return resp
        return _FakeResp({}, 404)


@pytest.fixture
def stub(monkeypatch):
    routes = {
        # Los prefijos más específicos van primero (coincidencia por startswith).
        "https://api.github.com/repos/o/r/commits/main/status": _FakeResp(
            {
                "statuses": [
                    {
                        "context": "Cloudflare Pages",
                        "state": "success",
                        "target_url": "https://pages.dev/abc",
                        "description": "Deployment complete",
                    },
                    {
                        "context": "ci / tests",
                        "state": "success",
                        "target_url": "",
                        "description": "",
                    },
                ]
            }
        ),
        "https://api.github.com/repos/o/r/commits/main/check-runs": _FakeResp(
            {
                "check_runs": [
                    {
                        "name": "pages-build-deployment",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/o/r/checks/1",
                        "output": {},
                    }
                ]
            }
        ),
        "https://api.github.com/repos/o/r": _FakeResp({"default_branch": "main"}),
    }
    monkeypatch.setattr(
        adapter_mod.httpx, "AsyncClient", lambda **kwargs: _FakeClient(routes)
    )


async def test_list_external_checks_reads_statuses_and_checks(stub):
    checks = await GithubApiAdapter().list_external_checks(
        GithubRepoId(owner="o", repo="r")
    )
    names = [c.name for c in checks]
    assert "Cloudflare Pages" in names
    assert "pages-build-deployment" in names
    assert all(c.state == "success" for c in checks if "loudflare" in c.name)


def test_normalize_state():
    assert _normalize_state("success") == "success"
    assert _normalize_state("error") == "failure"
    assert _normalize_state("pending") == "pending"


def test_normalize_check_run():
    assert _normalize_check_run("completed", "success") == "success"
    assert _normalize_check_run("completed", "failure") == "failure"
    assert _normalize_check_run("in_progress", None) == "pending"
