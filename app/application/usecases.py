"""Application use cases — orchestrate domain + ports, no HTTP/SQL here."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.ports import CheckRepository, GithubGateway, RepoRepository
from app.domain.repo import DeployCheck, GithubRepoId, TrackedRepo
from app.domain.services import evaluate_deploy_status


class RepoNotFound(Exception):
    pass


class RepoAlreadyTracked(Exception):
    pass


class GithubError(Exception):
    pass


@dataclass
class RepoWithStatus:
    repo: TrackedRepo
    check: DeployCheck | None


async def track_repo(raw_url: str, repos: RepoRepository) -> TrackedRepo:
    repo_id = GithubRepoId.parse(raw_url)
    if repos.get_by_full_name(repo_id.full_name):
        raise RepoAlreadyTracked(f"{repo_id.full_name} is already tracked.")
    tracked = TrackedRepo.create(repo_id)
    return repos.add(tracked)


def list_repos_with_status(
    repos: RepoRepository, checks: CheckRepository
) -> list[RepoWithStatus]:
    return [RepoWithStatus(repo=r, check=checks.get_last(r.id)) for r in repos.list()]


async def check_repo_now(
    repo_id: str,
    repos: RepoRepository,
    checks: CheckRepository,
    github: GithubGateway,
) -> DeployCheck:
    tracked = repos.get(repo_id)
    if tracked is None:
        raise RepoNotFound(repo_id)
    gid = GithubRepoId(owner=tracked.owner, repo=tracked.repo)
    try:
        workflows = await github.list_workflows(gid)
        runs = await github.list_runs(gid)
    except Exception as exc:
        raise GithubError(str(exc)) from exc
    status = evaluate_deploy_status(workflows, runs)
    return checks.save(DeployCheck.create(tracked.id, status))
