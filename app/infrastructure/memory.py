"""Infrastructure: in-memory fakes for unit tests."""
from __future__ import annotations

from app.domain.repo import DeployCheck, TrackedRepo


class InMemoryRepos:
    def __init__(self, seed: list[TrackedRepo] | None = None):
        self._items: dict[str, TrackedRepo] = {r.id: r for r in (seed or [])}

    def add(self, repo: TrackedRepo) -> TrackedRepo:
        self._items[repo.id] = repo
        return repo

    def list(self) -> list[TrackedRepo]:
        return list(self._items.values())

    def get(self, repo_id: str) -> TrackedRepo | None:
        return self._items.get(repo_id)

    def get_by_full_name(self, full_name: str) -> TrackedRepo | None:
        return next(
            (r for r in self._items.values() if r.full_name == full_name), None
        )

    def remove(self, repo_id: str) -> bool:
        return self._items.pop(repo_id, None) is not None


class InMemoryChecks:
    def __init__(self):
        self._last: dict[str, DeployCheck] = {}

    def save(self, check: DeployCheck) -> DeployCheck:
        self._last[check.repo_id] = check
        return check

    def get_last(self, repo_id: str) -> DeployCheck | None:
        return self._last.get(repo_id)
