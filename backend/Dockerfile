FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# ffmpeg: the AI package converts browser audio (webm/mp4/ogg) to 16 kHz wav
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY zolo ./zolo
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --create-home zolo && chown -R zolo /app
USER zolo
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn zolo.api.main:create_app --factory --host 0.0.0.0 --port 8000"]
