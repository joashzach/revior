"""Error envelope (PRD §12): {"error": {"code", "message", "details"}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import structlog

log = structlog.get_logger()

ERROR_STATUS = {
    "VALIDATION_ERROR": 422,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "INVALID_STATE": 409,
    "SEAT_UNAVAILABLE": 409,
    "ALLOCATION_IN_PROGRESS": 409,
    "BATCH_CLOSED": 409,
    "HOLD_EXPIRED": 409,
    "POD_FULL": 409,
    "RATE_LIMITED": 429,
    "IDEMPOTENCY_CONFLICT": 409,
}

_HTTP_TO_CODE = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 429: "RATE_LIMITED"}


class AppError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        if code not in ERROR_STATUS:
            raise ValueError(f"unknown error code {code}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = ERROR_STATUS[code]
        super().__init__(message)


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(envelope(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errs = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            envelope("VALIDATION_ERROR", "Request validation failed", {"errors": errs}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = _HTTP_TO_CODE.get(exc.status_code, "VALIDATION_ERROR")
        return JSONResponse(
            envelope(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.error("unhandled_exception", path=request.url.path, exc_info=exc)
        return JSONResponse(
            envelope("INTERNAL_ERROR", "Internal server error"), status_code=500
        )
