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
COPY alembic.ini docker-entrypoint.sh ./
# clips for the common amounts, copied onto the audio disk at start (see the entrypoint)
COPY audio_seed ./audio_seed
# the audio cache lives on a volume mounted at /data/audio (AUDIO_CACHE_DIR)
RUN useradd --create-home zolo && mkdir -p /data/audio && chown -R zolo /app /data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# starts as root only to fix the disk's owner, then drops to the zolo user (see the script)
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn zolo.api.main:create_app --factory --host 0.0.0.0 --port 8000"]
