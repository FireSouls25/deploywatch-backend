"""Ports (interfaces). Infrastructure implements these; domain never imports infra."""
from __future__ import annotations

from typing import Protocol

from .repo import DeployCheck, GithubRepoId, RunInfo, TrackedRepo, WorkflowInfo


class GithubGateway(Protocol):
    async def list_workflows(self, repo: GithubRepoId) -> list[WorkflowInfo]:
        ...

    async def list_runs(
        self, repo: GithubRepoId, workflow_name: str | None = None
    ) -> list[RunInfo]:
        ...


class RepoRepository(Protocol):
    def add(self, repo: TrackedRepo) -> TrackedRepo:
        ...

    def list(self) -> list[TrackedRepo]:
        ...

    def get(self, repo_id: str) -> TrackedRepo | None:
        ...

    def get_by_full_name(self, full_name: str) -> TrackedRepo | None:
        ...

    def remove(self, repo_id: str) -> bool:
        ...


class CheckRepository(Protocol):
    def save(self, check: DeployCheck) -> DeployCheck:
        ...

    def get_last(self, repo_id: str) -> DeployCheck | None:
        ...
