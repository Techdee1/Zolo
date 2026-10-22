"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from zolo.api import (
    health,
    routes_agent,
    routes_audio,
    routes_auth,
    routes_demo,
    routes_dev,
    routes_me,
    routes_passkeys,
    routes_requests,
)
from zolo.api.errors import install_error_handlers
from zolo.api.middleware import RequestContextMiddleware
from zolo.api.services import Overrides
from zolo.core.config import Settings, get_settings
from zolo.core.db import make_engine, make_sessionmaker
from zolo.core.logging import configure_logging
from zolo.tools.render_clips import log_audio_inventory


def create_app(settings: Settings | None = None, *, overrides: Overrides | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url, settings.db_pool_size, settings.db_max_overflow)
        app.state.engine = engine
        log_audio_inventory()
        app.state.sessionmaker = make_sessionmaker(engine)
        yield
        await engine.dispose()

    app = FastAPI(
        title="Zolo API",
        version="0.1.0",
        description="Anyone can propose a payment. Only the account holder approves it.",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.overrides = overrides or Overrides()

    # Added last runs first: CORS answers preflights before anything else touches them.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Demo-Token", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(routes_passkeys.router)
    app.include_router(routes_agent.router)
    app.include_router(routes_requests.router)
    app.include_router(routes_me.router)
    app.include_router(routes_audio.router)
    if settings.demo_mode:
        # Mock login and the dev page exist only in demo mode: without it the routes are absent.
        app.include_router(routes_auth.router)
        app.include_router(routes_dev.router)
        app.include_router(routes_demo.router)
    return app
