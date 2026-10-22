"""Start the real-backend run with no passkeys stored, so 'no passkey yet' is a true starting state.
Run from ../backend with its environment (the Playwright config does this)."""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE passkey_credentials, webauthn_challenges"))
    await engine.dispose()


asyncio.run(main())
