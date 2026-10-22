"""`python -m zolo.seed --if-empty` seeds a fresh database once and never wipes a live one."""

import subprocess
import sys

from sqlalchemy import text

from tests.conftest import make_settings
from zolo.demo.seed import reset_demo


async def _run(database_url: str, *args: str) -> str:
    import os

    env = {**os.environ, "DATABASE_URL": database_url}
    done = subprocess.run(
        [sys.executable, "-m", "zolo.seed", *args], env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


async def test_if_empty_seeds_once_and_then_leaves_the_data_alone(sessionmaker) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings()
    async with sessionmaker() as s, s.begin():
        await s.execute(text("TRUNCATE customers, agents, bank_accounts, saved_recipients CASCADE"))
    assert "seeded" in await _run(settings.database_url, "--if-empty")
    async with sessionmaker() as s:
        assert (await s.execute(text("SELECT count(*) FROM customers"))).scalar_one() == 1
        await s.execute(text("UPDATE customers SET display_name = 'Changed'"))
        await s.commit()
    assert "already seeded" in await _run(settings.database_url, "--if-empty")
    async with sessionmaker() as s:
        name = (await s.execute(text("SELECT display_name FROM customers"))).scalar_one()
        assert name == "Changed"  # not wiped
    await reset_demo(sessionmaker, settings)  # leave the test database as the others expect
