"""RFC 9457 problem details. Every error has a stable uppercase `code` the frontend maps to a
spoken message; `detail` is for developers and is never shown to customers."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from zolo.core.errors import ApiError, ErrorCode

log = logging.getLogger("zolo.api")
PROBLEM_JSON = "application/problem+json"


class Problem(BaseModel):
    type: str
    title: str
    status: int
    code: ErrorCode
    detail: str = ""


def problem_response(status: int, code: ErrorCode, title: str, detail: str = "") -> JSONResponse:
    body = Problem(
        type=f"https://zolo.app/problems/{code.value.lower().replace('_', '-')}",
        title=title, status=status, code=code, detail=detail,
    )  # fmt: skip
    return JSONResponse(body.model_dump(mode="json"), status_code=status, media_type=PROBLEM_JSON)


_HTTP_CODES = {
    401: (ErrorCode.UNAUTHENTICATED, "Authentication required"),
    403: (ErrorCode.FORBIDDEN, "Not allowed"),
    404: (ErrorCode.NOT_FOUND, "Not found"),
    405: (ErrorCode.NOT_FOUND, "Method not allowed"),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names and locations only: the submitted values may hold personal data.
        where = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        return problem_response(422, ErrorCode.VALIDATION_ERROR, "Invalid request", where)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = _HTTP_CODES.get(exc.status_code, (ErrorCode.INTERNAL_ERROR, "Request failed"))
        return problem_response(exc.status_code, code, title)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled", extra={"event": "unhandled", "error_type": type(exc).__name__})
        return problem_response(500, ErrorCode.INTERNAL_ERROR, "Something went wrong")
