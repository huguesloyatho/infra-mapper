"""Rate limiting middleware for Infra-Mapper."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_settings


def get_real_ip(request: Request) -> str:
    """
    Get the real client IP address, considering reverse proxies.

    Checks headers in order:
    1. X-Forwarded-For (most common)
    2. X-Real-IP
    3. CF-Connecting-IP (Cloudflare)
    4. Falls back to direct connection IP
    """
    # X-Forwarded-For can contain multiple IPs: client, proxy1, proxy2, ...
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Get the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # X-Real-IP is typically set by nginx
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Cloudflare specific header
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Fallback to direct connection
    return get_remote_address(request)


def create_limiter() -> Limiter:
    """Create and configure the rate limiter."""
    settings = get_settings()

    if not settings.rate_limit_enabled:
        # Return a limiter that doesn't actually limit
        return Limiter(
            key_func=get_real_ip,
            enabled=False
        )

    return Limiter(
        key_func=get_real_ip,
        default_limits=[f"{settings.rate_limit_requests}/{settings.rate_limit_window}seconds"],
        enabled=True,
        # Store in memory (consider Redis for multi-instance deployments)
        storage_uri="memory://",
    )


# Global limiter instance
limiter = create_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "error": str(exc.detail),
            "retry_after": exc.detail.split("per")[1].strip() if "per" in exc.detail else "60 seconds"
        },
        headers={"Retry-After": "60"}
    )
