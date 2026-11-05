from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.application import usecases
from app.domain.repo import DeployOutcome

router = APIRouter(prefix="/api")


class TrackRepoIn(BaseModel):
    url: str


def _check_to_dict(check) -> dict | None:
    if check is None:
        return None
    return {
        "outcome": check.outcome.value,
        "message": check.message,
        "workflow_name": check.workflow_name,
        "run_url": check.run_url,
        "checked_at": check.checked_at.isoformat(),
        "needs_attention": check.outcome
        in (DeployOutcome.FAILURE, DeployOutcome.NO_DEPLOY_SETUP, DeployOutcome.NEVER_DEPLOYED),
        "provider": check.provider,
    }


@router.post("/repos", status_code=201)
async def track_repo(body: TrackRepoIn):
    # deps resolved via app-level dependency_overrides in main.py; kept simple here
    from app.api.deps import get_repo_repo

    repos = get_repo_repo()
    try:
        tracked = await usecases.track_repo(body.url, repos)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except usecases.RepoAlreadyTracked as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": tracked.id, "full_name": tracked.full_name}


@router.get("/repos")
def list_repos():
    from app.api.deps import get_check_repo, get_repo_repo

    items = usecases.list_repos_with_status(get_repo_repo(), get_check_repo())
    return [
        {
            "id": it.repo.id,
            "full_name": it.repo.full_name,
            "url": f"https://github.com/{it.repo.full_name}",
            "last_check": _check_to_dict(it.check),
        }
        for it in items
    ]


@router.post("/repos/{repo_id}/check")
async def check_now(repo_id: str):
    from app.api.deps import get_check_repo, get_github, get_repo_repo

    try:
        check = await usecases.check_repo_now(
            repo_id, get_repo_repo(), get_check_repo(), get_github()
        )
    except usecases.RepoNotFound:
        raise HTTPException(404, "Tracked repo not found.")
    except usecases.GithubError as exc:
        raise HTTPException(502, f"GitHub lookup failed: {exc}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"last_check": _check_to_dict(check)}


@router.delete("/repos/{repo_id}", status_code=204)
def remove_repo(repo_id: str):
    from app.api.deps import get_repo_repo

    if not get_repo_repo().remove(repo_id):
        raise HTTPException(404, "Tracked repo not found.")


@router.get("/health")
def health():
    return {"status": "ok"}
