"""API fixtures: the real app on the seeded database, a controllable clock and rate limiter, and
two logged-in browsers (an agent's and a customer's), each with its own cookie jar."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.test_consent_engine import Clock, StubAudio
from tests.webauthn_software import SoftwareAuthenticator
from zolo.api.main import create_app
from zolo.api.services import Overrides
from zolo.core.config import Settings
from zolo.core.ratelimit import RateLimiter
from zolo.demo.seed import reset_demo

AMAKA_PHONE, BISI_PHONE, MAMA_PHONE = "+2348011111111", "+2348022222222", "+2348033333333"


class MonotonicClock:
    """The rate limiter's clock, so lock and window expiry need no sleeping."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limiter_clock() -> MonotonicClock:
    return MonotonicClock()


@pytest.fixture
def phone(settings: Settings) -> SoftwareAuthenticator:
    return SoftwareAuthenticator(settings.rp_id, settings.origins[0])


async def build_app(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: Clock,
    limiter_clock: MonotonicClock,
) -> FastAPI:
    await reset_demo(sessionmaker, settings)
    app = create_app(
        settings,
        overrides=Overrides(clock=clock, audio=StubAudio(), limiter=RateLimiter(limiter_clock)),
    )
    app.state.sessionmaker = sessionmaker
    return app


@pytest.fixture
async def api(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: Clock,
    limiter_clock: MonotonicClock,
) -> FastAPI:
    return await build_app(sessionmaker, settings, clock, limiter_clock)


def browser(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def login(client: AsyncClient, phone: str, otp: str = "123456") -> None:
    r = await client.post("/auth/mock-login", json={"phone": phone, "otp": otp})
    assert r.status_code == 200, r.text


@pytest.fixture
async def anonymous(api: FastAPI) -> AsyncIterator[AsyncClient]:
    async with browser(api) as c:
        yield c


@pytest.fixture
async def agent(api: FastAPI) -> AsyncIterator[AsyncClient]:
    async with browser(api) as c:
        await login(c, BISI_PHONE)
        yield c


@pytest.fixture
async def customer(api: FastAPI) -> AsyncIterator[AsyncClient]:
    async with browser(api) as c:
        await login(c, AMAKA_PHONE)
        yield c
