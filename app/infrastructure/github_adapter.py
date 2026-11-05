"""Infrastructure: GitHub REST adapter (httpx). No domain logic here."""
from __future__ import annotations

import httpx

from app.domain.repo import GithubRepoId, RunInfo, WorkflowInfo


class GithubApiAdapter:
    def __init__(self, base_url: str = "https://api.github.com", token: str | None = None):
        self._base = base_url.rstrip("/")
        self._headers = {"Accept": "application/vnd.github+json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    async def list_workflows(self, repo: GithubRepoId) -> list[WorkflowInfo]:
        url = f"{self._base}/repos/{repo.full_name}/actions/workflows"
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise FileNotFoundError(f"Repo {repo.full_name} not found on GitHub.")
            resp.raise_for_status()
            data = resp.json()
        return [
            WorkflowInfo(
                workflow_id=w["id"], name=w.get("name", ""), path=w.get("path", "")
            )
            for w in data.get("workflows", [])
        ]

    async def list_runs(
        self, repo: GithubRepoId, workflow_name: str | None = None
    ) -> list[RunInfo]:
        url = f"{self._base}/repos/{repo.full_name}/actions/runs?per_page=10"
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        return [
            RunInfo(
                name=r.get("name", ""),
                status=r.get("status", ""),
                conclusion=r.get("conclusion"),
                html_url=r.get("html_url", ""),
                created_at=r.get("created_at", ""),
            )
            for r in data.get("workflow_runs", [])
        ]
