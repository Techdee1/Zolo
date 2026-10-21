from typing import Any

from zolo.api.errors import Problem


def problems(*items: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for the problem+json errors a route can return."""
    return {status: {"model": Problem, "description": text} for status, text in items}


UNAUTHENTICATED = (401, "UNAUTHENTICATED: log in first")
FORBIDDEN = (403, "FORBIDDEN: wrong role for this endpoint")
NOT_FOUND = (404, "NOT_FOUND: no such request, or it is not yours")
RATE_LIMITED = (429, "RATE_LIMITED: slow down; see the Retry-After header")
