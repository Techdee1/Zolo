"""python -m zolo.seed: put the demo back to its starting state (same as POST /demo/reset)."""

import asyncio

from zolo.core.config import get_settings
from zolo.core.db import make_engine, make_sessionmaker
from zolo.demo.seed import reset_demo


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        summary = await reset_demo(make_sessionmaker(engine), settings)
    finally:
        await engine.dispose()
    # Counts only: names and numbers do not belong in logs or terminals that get screen-shared.
    print(
        f"seeded {summary.customers} customer, {summary.agents} agents, "
        f"{summary.accounts} accounts, {summary.recipients} saved recipients"
    )


if __name__ == "__main__":
    asyncio.run(main())
