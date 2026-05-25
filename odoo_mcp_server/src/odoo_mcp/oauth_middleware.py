"""
Cookie → Authorization-header session injector middleware.

Summary:
    Browser-flow clients carry their session token in an HttpOnly cookie.
    Downstream MCP code only knows how to read Authorization: Bearer,
    so this middleware rewrites the request headers in-place when:
      - the path is not in the public allow-list,
      - no Authorization header is already present,
      - and a session cookie is set.
    The bearer-token flow bypasses this entirely because those clients
    already send their own Authorization header.

Version: 0.2.0
Execution context: library (mounted by build_oauth_ui_app in oauth.py)
"""

from __future__ import annotations

from typing import Any, Callable

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SessionInjectorMiddleware(BaseHTTPMiddleware):
    """Inject a signed session token from a cookie into the bearer auth header."""

    def __init__(self, app: ASGIApp, cookie_name: str, public_paths: set[str]) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        # Set, not list — O(1) membership check on every request.
        self.public_paths = public_paths

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # Public OAuth endpoints (login, callback, .well-known, /auth/*)
        # are not subject to session injection — they handle auth themselves.
        if request.url.path in self.public_paths:
            return await call_next(request)
        # Bearer-flow clients (Claude Desktop, scripts) already set this
        # header; never overwrite a caller-provided Authorization.
        if request.headers.get("authorization"):
            return await call_next(request)
        # Browser-flow clients carry the token in an HttpOnly cookie.
        # Promote it to Authorization so the downstream MCP auth chain
        # treats both transports identically.
        cookie_token = request.cookies.get(self.cookie_name)
        if cookie_token:
            headers = MutableHeaders(scope=request.scope)
            headers["authorization"] = f"Bearer {cookie_token}"
        return await call_next(request)
