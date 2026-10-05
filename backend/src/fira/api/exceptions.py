import logging
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

logger = logging.getLogger("fira.api.exceptions")

def register_exception_handlers(app: FastAPI) -> None:
    """Register sanitized, enterprise error handlers to prevent information disclosure (OWASP A05)."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            "HTTP %d error on %s %s: %s (req_id=%s)",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
            req_id,
        )
        headers = dict(exc.headers or {})
        headers["X-Request-ID"] = req_id
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": f"https://errors.fira.local/http-{exc.status_code}",
                "title": "HTTP Error",
                "status": exc.status_code,
                "detail": exc.detail,
                "request_id": req_id,
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        # Sanitize validation errors to avoid leaking internal data structures
        sanitized_errors = []
        for err in exc.errors():
            sanitized_errors.append({
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg"),
                "type": err.get("type"),
            })

        logger.info("Validation failure on %s (req_id=%s): %s", request.url.path, req_id, sanitized_errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": "https://errors.fira.local/validation-error",
                "title": "Unprocessable Entity",
                "status": 422,
                "detail": "Input validation failed. Check parameters.",
                "errors": sanitized_errors,
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        # Log full internal stack trace securely on the server
        logger.error(
            "Unhandled server error on %s %s (req_id=%s)",
            request.method,
            request.url.path,
            req_id,
            exc_info=exc,
        )
        # Never leak raw stack traces or internal exception details to client
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "https://errors.fira.local/internal-server-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected server error occurred. Please contact system support with your Request ID.",
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id},
        )
