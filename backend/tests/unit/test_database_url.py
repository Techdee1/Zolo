"""Hosts hand out plain Postgres URLs; the app needs the asyncpg driver. Anything else is refused."""

import pytest
from pydantic import ValidationError

from zolo.core.config import Settings

BASE = {"session_secret": "x" * 32}


@pytest.mark.parametrize("given", ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"])
def test_plain_postgres_urls_are_upgraded_to_asyncpg(given: str) -> None:
    s = Settings(database_url=given, **BASE)  # type: ignore[arg-type]
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"


def test_an_asyncpg_url_is_left_alone() -> None:
    url = "postgresql+asyncpg://u:p@h:5432/d"
    assert Settings(database_url=url, **BASE).database_url == url  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad", ["mysql://u:p@h/d", "sqlite:///x.db", "", "postgresql+psycopg://u:p@h/d"]
)
def test_other_databases_are_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=bad, **BASE)  # type: ignore[arg-type]
