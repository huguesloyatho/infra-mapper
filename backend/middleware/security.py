"""Security middleware for Infra-Mapper."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        response = await call_next(request)

        if settings.security_headers_enabled:
            # Content Security Policy
            if settings.csp_policy:
                response.headers["Content-Security-Policy"] = settings.csp_policy

            # X-Frame-Options (prevent clickjacking)
            if settings.x_frame_options:
                response.headers["X-Frame-Options"] = settings.x_frame_options

            # X-Content-Type-Options (prevent MIME sniffing)
            response.headers["X-Content-Type-Options"] = "nosniff"

            # X-XSS-Protection (legacy but still useful for older browsers)
            response.headers["X-XSS-Protection"] = "1; mode=block"

            # Referrer-Policy
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Permissions-Policy (restrict browser features)
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response
