"""Infrastructure: SQLAlchemy models + repository implementations."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.domain.repo import DeployCheck, DeployOutcome, TrackedRepo


class Base(DeclarativeBase):
    pass


class TrackedRepoRow(Base):
    __tablename__ = "tracked_repos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeployCheckRow(Base):
    __tablename__ = "deploy_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    workflow_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


class SqlRepoRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sessions = session_factory

    def add(self, repo: TrackedRepo) -> TrackedRepo:
        with self._sessions() as s:
            s.add(
                TrackedRepoRow(
                    id=repo.id, owner=repo.owner, repo=repo.repo,
                    created_at=repo.created_at,
                )
            )
            s.commit()
        return repo

    def list(self) -> list[TrackedRepo]:
        with self._sessions() as s:
            rows = s.query(TrackedRepoRow).order_by(TrackedRepoRow.created_at).all()
            return [
                TrackedRepo(id=r.id, owner=r.owner, repo=r.repo, created_at=r.created_at)
                for r in rows
            ]

    def get(self, repo_id: str) -> TrackedRepo | None:
        with self._sessions() as s:
            r = s.get(TrackedRepoRow, repo_id)
            return (
                TrackedRepo(id=r.id, owner=r.owner, repo=r.repo, created_at=r.created_at)
                if r else None
            )

    def get_by_full_name(self, full_name: str) -> TrackedRepo | None:
        owner, _, name = full_name.partition("/")
        with self._sessions() as s:
            r = (
                s.query(TrackedRepoRow)
                .filter_by(owner=owner, repo=name).first()
            )
            return (
                TrackedRepo(id=r.id, owner=r.owner, repo=r.repo, created_at=r.created_at)
                if r else None
            )

    def remove(self, repo_id: str) -> bool:
        with self._sessions() as s:
            r = s.get(TrackedRepoRow, repo_id)
            if not r:
                return False
            s.delete(r)
            s.query(DeployCheckRow).filter_by(repo_id=repo_id).delete()
            s.commit()
            return True


class SqlCheckRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sessions = session_factory

    def save(self, check: DeployCheck) -> DeployCheck:
        with self._sessions() as s:
            s.add(
                DeployCheckRow(
                    id=check.id, repo_id=check.repo_id,
                    outcome=check.outcome.value, message=check.message,
                    workflow_name=check.workflow_name, run_url=check.run_url,
                    checked_at=check.checked_at,
                )
            )
            s.commit()
        return check

    def get_last(self, repo_id: str) -> DeployCheck | None:
        with self._sessions() as s:
            r = (
                s.query(DeployCheckRow)
                .filter_by(repo_id=repo_id)
                .order_by(DeployCheckRow.checked_at.desc()).first()
            )
            return (
                DeployCheck(
                    id=r.id, repo_id=r.repo_id,
                    outcome=DeployOutcome(r.outcome), message=r.message,
                    workflow_name=r.workflow_name, run_url=r.run_url,
                    checked_at=r.checked_at,
                )
                if r else None
            )
