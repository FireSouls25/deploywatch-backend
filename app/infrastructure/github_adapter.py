"""Infrastructure: GitHub REST adapter (httpx). No domain logic here."""
from __future__ import annotations

import httpx

from app.domain.repo import (
    DeploymentInfo,
    EnvironmentInfo,
    ExternalCheckInfo,
    GithubRepoId,
    RunInfo,
    WorkflowInfo,
)


def _normalize_state(state: str) -> str:
    """Commit status -> success | failure | pending."""
    s = state.lower()
    if s == "success":
        return "success"
    if s in ("failure", "error"):
        return "failure"
    return "pending"


def _normalize_check_run(status: str, conclusion: str | None) -> str:
    """Check run -> success | failure | pending."""
    if status != "completed":
        return "pending"
    if conclusion == "success":
        return "success"
    if conclusion in ("failure", "timed_out", "action_required"):
        return "failure"
    return "pending"


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

    async def list_external_checks(
        self, repo: GithubRepoId
    ) -> list[ExternalCheckInfo]:
        """Statuses y checks del HEAD de la rama por defecto.

        Cubre el caso Cloudflare-desde-el-panel: sin Actions propio ni
        Deployments, la plataforma reporta aquí (contexto 'Cloudflare
        Pages', checks de 'pages-build-deployment', etc.).
        """
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            info = await client.get(f"{self._base}/repos/{repo.full_name}")
            if info.status_code == 404:
                raise FileNotFoundError(
                    f"Repo {repo.full_name} not found on GitHub."
                )
            info.raise_for_status()
            branch = info.json().get("default_branch", "main")

            out: list[ExternalCheckInfo] = []
            status_resp = await client.get(
                f"{self._base}/repos/{repo.full_name}/commits/{branch}/status"
            )
            if status_resp.is_success:
                for st in status_resp.json().get("statuses", []):
                    out.append(
                        ExternalCheckInfo(
                            kind="status",
                            name=st.get("context", ""),
                            state=_normalize_state(st.get("state", "")),
                            url=st.get("target_url", "") or "",
                            description=st.get("description", "") or "",
                        )
                    )
            checks_resp = await client.get(
                f"{self._base}/repos/{repo.full_name}/commits/"
                f"{branch}/check-runs?per_page=20"
            )
            if checks_resp.is_success:
                for run in checks_resp.json().get("check_runs", []):
                    out.append(
                        ExternalCheckInfo(
                            kind="check",
                            name=run.get("name", ""),
                            state=_normalize_check_run(
                                run.get("status", ""), run.get("conclusion")
                            ),
                            url=run.get("html_url", "") or "",
                            description=run.get("output", {}).get("title", "")
                            or "",
                        )
                    )
            return out

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
