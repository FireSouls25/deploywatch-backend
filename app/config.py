from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./deploywatch.db")
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_api: str = "https://api.github.com"


settings = Settings()
