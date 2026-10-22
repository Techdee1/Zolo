"""Serves pre-rendered readback audio from the cache. The key is a SHA-256 of the exact words,
language and voice, so a URL cannot be guessed without knowing the sentence."""

import re

from fastapi import APIRouter, Response

from zolo.api.deps import ServicesDep
from zolo.core.errors import ApiError, ErrorCode

router = APIRouter(tags=["audio"])
_KEY = re.compile(r"^[0-9a-f]{64}$")


@router.get(
    "/voice/audio/{key}.mp3",
    summary="Pre-rendered readback audio",
    responses={200: {"content": {"audio/mpeg": {}}}, 404: {"description": "NOT_FOUND"}},
)
async def audio(key: str, services: ServicesDep) -> Response:
    clip = services.audio_cache.get(key) if _KEY.match(key) else None
    if clip is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")
    return Response(
        clip.data, media_type=clip.mime, headers={"Cache-Control": "private, max-age=3600"}
    )
