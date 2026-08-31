"""Exception Handlers for FastAPI"""

from fastapi import Request
from fastapi.responses import JSONResponse

from src.exceptions.base import TokenServerError
from src.logging import get_logger

logger = get_logger("exceptions")


async def token_server_exception_handler(
    request: Request,
    exc: TokenServerError
) -> JSONResponse:
    """Handle TokenServerError exceptions

    Converts our custom exceptions to proper JSON responses.
    """
    logger.warning(
        f"TokenServerError: {exc.code}",
        error_code=exc.code,
        error_message=exc.message,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app

    Usage:
        app = FastAPI()
        register_exception_handlers(app)
    """
    app.add_exception_handler(TokenServerError, token_server_exception_handler)
