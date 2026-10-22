"""python -m zolo.seed: put the demo back to its starting state (same as POST /demo/reset).

`--if-empty` seeds only when there are no customers yet, so it is safe to run on every start of a
deployment: the first start seeds, a restart leaves requests and balances alone."""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zolo.core.config import get_settings
from zolo.core.db import make_engine, make_sessionmaker
from zolo.demo.seed import reset_demo


async def _is_empty(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    async with sessionmaker() as session:
        count = (await session.execute(text("SELECT count(*) FROM customers"))).scalar_one()
        return bool(count == 0)


async def main(if_empty: bool = False) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        if if_empty and not await _is_empty(make_sessionmaker(engine)):
            print("already seeded, nothing changed")
            return
        summary = await reset_demo(make_sessionmaker(engine), settings)
    finally:
        await engine.dispose()
    # Counts only: names and numbers do not belong in logs or terminals that get screen-shared.
    print(
        f"seeded {summary.customers} customer, {summary.agents} agents, "
        f"{summary.accounts} accounts, {summary.recipients} saved recipients"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true", help="only seed an empty database")
    asyncio.run(main(parser.parse_args().if_empty))
