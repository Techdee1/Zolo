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


def test_a_hosted_database_can_be_asked_to_use_ssl() -> None:
    s = Settings(database_url="postgres://u:p@h:5432/d", database_ssl="require", **BASE)  # type: ignore[arg-type]
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d?ssl=require"
    again = Settings(  # type: ignore[arg-type]
        database_url="postgresql+asyncpg://u:p@h/d?application_name=z",
        database_ssl="require",
        **BASE,
    )
    assert again.database_url.endswith("?application_name=z&ssl=require")
    kept = Settings(
        database_url="postgresql+asyncpg://u:p@h/d?ssl=disable", database_ssl="require", **BASE
    )  # type: ignore[arg-type]
    assert kept.database_url.endswith("ssl=disable")  # an explicit choice is never overridden


def test_without_the_setting_the_url_is_untouched_and_the_pool_has_its_defaults() -> None:
    s = Settings(database_url="postgresql+asyncpg://u:p@localhost/d", **BASE)  # type: ignore[arg-type]
    assert s.database_url == "postgresql+asyncpg://u:p@localhost/d"
    assert (s.db_pool_size, s.db_max_overflow) == (10, 10)


def test_the_pool_can_be_capped_for_a_small_database() -> None:
    s = Settings(database_url="postgres://u:p@h/d", db_pool_size=4, db_max_overflow=2, **BASE)  # type: ignore[arg-type]
    assert s.db_pool_size + s.db_max_overflow == 6
