"""Infrastructure: GitHub REST adapter (httpx). No domain logic here."""
from __future__ import annotations

import httpx

from app.domain.repo import (
    DeploymentInfo,
    EnvironmentInfo,
    GithubRepoId,
    RunInfo,
    WorkflowInfo,
)


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

    async def list_deployments(self, repo: GithubRepoId) -> list[DeploymentInfo]:
        """Lee los deployments que publican las plataformas externas.

        Cloudflare Pages, Vercel o Netlify crean aquí un registro por cada
        despliegue cuando su integración de GitHub está conectada.
        """
        url = f"{self._base}/repos/{repo.full_name}/deployments?per_page=5"
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            out: list[DeploymentInfo] = []
            for dep in items[:5]:
                state = await self._latest_deployment_state(
                    client, repo, dep["id"]
                )
                out.append(
                    DeploymentInfo(
                        deployment_id=dep["id"],
                        environment=dep.get("environment", ""),
                        state=state,
                        target_url=dep.get("payload", {}).get("web_url", "")
                        or "",
                        created_at=dep.get("created_at", ""),
                    )
                )
            return out

    async def _latest_deployment_state(
        self, client: httpx.AsyncClient, repo: GithubRepoId, deployment_id: int
    ) -> str:
        url = (
            f"{self._base}/repos/{repo.full_name}/deployments/"
            f"{deployment_id}/statuses?per_page=1"
        )
        resp = await client.get(url)
        if not resp.is_success:
            return "pending"
        items = resp.json()
        return items[0].get("state", "pending") if items else "pending"

    async def list_environments(self, repo: GithubRepoId) -> list[EnvironmentInfo]:
        url = f"{self._base}/repos/{repo.full_name}/environments"
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
        return [
            EnvironmentInfo(name=e.get("name", ""))
            for e in data.get("environments", [])
        ]
