"""DeployWatch domain layer — pure Python, no framework imports."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class DeployOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "in_progress"
    NEVER_DEPLOYED = "never_deployed"
    NO_DEPLOY_SETUP = "no_deploy_setup"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GithubRepoId:
    owner: str
    repo: str

    @classmethod
    def parse(cls, raw: str) -> GithubRepoId:
        """Accept 'owner/repo' or full github.com URLs."""
        raw = raw.strip().rstrip("/").removesuffix(".git")
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+)\s*$", raw)
        if m:
            owner, repo = m.group(1), m.group(2)
        elif re.fullmatch(r"[\w.\-]+/[\w.\-]+", raw):
            owner, repo = raw.split("/", 1)
        else:
            raise ValueError(
                f"Invalid repo reference {raw!r}. Use 'owner/repo' or "
                "'https://github.com/owner/repo'."
            )
        return cls(owner=owner.lower(), repo=repo.lower())

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.full_name}"


@dataclass(frozen=True)
class WorkflowInfo:
    workflow_id: int
    name: str
    path: str

    def looks_like_deploy(self) -> bool:
        blob = f"{self.name} {self.path}".lower()
        return "deploy" in blob


@dataclass(frozen=True)
class RunInfo:
    name: str
    status: str  # queued | in_progress | completed
    conclusion: str | None  # success | failure | cancelled | ...
    html_url: str
    created_at: str = ""


@dataclass(frozen=True)
class DeploymentInfo:
    """Un despliegue registrado en la API de Deployments de GitHub.

    Aquí aparecen los despliegues de plataformas externas (Cloudflare Pages,
    Vercel, Netlify) cuando el repo tiene su integración de GitHub conectada,
    aunque no exista ningún workflow con 'deploy' en el nombre.
    """

    deployment_id: int
    environment: str
    state: str  # success | failure | error | pending | queued | in_progress
    target_url: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class EnvironmentInfo:
    name: str


@dataclass(frozen=True)
class DeployStatus:
    outcome: DeployOutcome
    message: str
    needs_attention: bool
    workflow_name: str | None = None
    run_url: str | None = None


@dataclass
class TrackedRepo:
    id: str
    owner: str
    repo: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, repo_id: GithubRepoId) -> TrackedRepo:
        return cls(id=str(uuid4()), owner=repo_id.owner, repo=repo_id.repo)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class DeployCheck:
    id: str
    repo_id: str
    outcome: DeployOutcome
    message: str
    workflow_name: str | None
    run_url: str | None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls, repo_id: str, status: DeployStatus
    ) -> DeployCheck:
        return cls(
            id=str(uuid4()),
            repo_id=repo_id,
            outcome=status.outcome,
            message=status.message,
            workflow_name=status.workflow_name,
            run_url=status.run_url,
        )
