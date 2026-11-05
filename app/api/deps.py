"""Composition root: wires infra into use cases. Routes import from here."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.infrastructure.db import (
    Base,
    SqlCheckRepository,
    SqlRepoRepository,
    ensure_provider_column,
    make_engine,
)
from app.infrastructure.github_adapter import GithubApiAdapter

_engine = make_engine(settings.database_url)
Base.metadata.create_all(_engine)
ensure_provider_column(_engine)
_session_factory = sessionmaker(bind=_engine)

_repo_repo = SqlRepoRepository(_session_factory)
_check_repo = SqlCheckRepository(_session_factory)


@lru_cache
def get_github() -> GithubApiAdapter:
    return GithubApiAdapter(base_url=settings.github_api, token=settings.github_token)


def get_repo_repo() -> SqlRepoRepository:
    return _repo_repo


def get_check_repo() -> SqlCheckRepository:
    return _check_repo
