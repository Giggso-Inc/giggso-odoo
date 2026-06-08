"""
Cookie → Authorization-header session injector middleware.
Accept-header normaliser middleware.

Summary:
    Browser-flow clients carry their session token in an HttpOnly cookie.
    Downstream MCP code only knows how to read Authorization: Bearer,
    so this middleware rewrites the request headers in-place when:
      - the path is not in the public allow-list,
      - no Authorization header is already present,
      - and a session cookie is set.
    The bearer-token flow bypasses this entirely because those clients
    already send their own Authorization header.

Implementation note — pure ASGI, NOT BaseHTTPMiddleware:
    Starlette's BaseHTTPMiddleware.call_next() spawns an internal
    background task to stream the request body. FastMCP's streamable-HTTP
    handler uses anyio task groups internally; anyio requires that a cancel
    scope is exited by the same task that entered it. When BaseHTTPMiddleware
    puts the downstream app in a different task, anyio raises:
        RuntimeError: Attempted to exit cancel scope in a different task
    which surfaces as a 500 for every spec-compliant MCP client (ADK, Prism7,
    Claude Desktop, etc.).

    The fix is to implement the middleware as a plain ASGI callable. We mutate
    scope["headers"] directly — same task, no background work, anyio never
    sees a task switch.

Version: 0.3.0
Execution context: library (mounted by build_oauth_ui_app in oauth.py)

AcceptNormalizerMiddleware
--------------------------
The MCP Streamable HTTP spec requires clients to send:
    Accept: application/json, text/event-stream

Standard HTTP clients (PowerShell Invoke-RestMethod, curl, httpx without
explicit headers) default to Accept: */* which does not contain
"application/json" literally.  The FastMCP layer rejects those requests
with 406 "Not Acceptable: Client must accept application/json".

This middleware intercepts every HTTP request and rewrites the Accept header
to include both required types if either is missing.  Clients already sending
the correct header are not touched.
"""

from __future__ import annotations

from http.cookies import SimpleCookie

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


class SessionInjectorMiddleware:
    """Inject a signed session token from a cookie into the bearer auth header.

    Pure ASGI implementation — does NOT extend BaseHTTPMiddleware so it is
    safe to wrap anyio-based streaming apps such as FastMCP.
    """

    def __init__(self, app: ASGIApp, cookie_name: str, public_paths: set[str]) -> None:
        self.app = app
        self.cookie_name = cookie_name
        # Set, not list — O(1) membership check on every request.
        self.public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only intercept HTTP requests — pass websocket/lifespan through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Public OAuth endpoints (login, callback, .well-known, /auth/*)
        # handle their own auth — do not inject into them.
        if path in self.public_paths:
            await self.app(scope, receive, send)
            return

        # Collect existing headers as a case-insensitive lookup.
        headers = MutableHeaders(scope=scope)

        # Bearer-flow clients (Claude Desktop, scripts, API keys) already set
        # Authorization — never overwrite a caller-provided value.
        if headers.get("authorization"):
            await self.app(scope, receive, send)
            return

        # Browser-flow clients carry the token in an HttpOnly cookie.
        # Parse the Cookie header directly from scope so we never need to
        # build a full Request object (avoids any starlette internals that
        # could interact badly with streaming bodies).
        raw_cookie = headers.get("cookie", "")
        cookie_token: str | None = None
        if raw_cookie:
            jar: SimpleCookie[str] = SimpleCookie()
            jar.load(raw_cookie)
            morsel = jar.get(self.cookie_name)
            if morsel is not None:
                cookie_token = morsel.value

        # Promote the cookie token to Authorization so the downstream MCP
        # auth chain treats browser and headless transports identically.
        if cookie_token:
            headers["authorization"] = f"Bearer {cookie_token}"

        # Hand off to the next app in the same task — no background task,
        # no anyio task-scope crossing.
        await self.app(scope, receive, send)


class AcceptNormalizerMiddleware:
    """Ensure every HTTP request carries the Accept types required by FastMCP.

    FastMCP's streamable-HTTP handler (mcp>=1.23) rejects requests whose
    Accept header does not contain "application/json".  Earlier versions also
    require "text/event-stream".  Generic HTTP clients (PowerShell, curl,
    httpx) default to Accept: */* which satisfies neither check.

    This middleware rewrites Accept to "application/json, text/event-stream"
    whenever either type is absent.  Clients already sending the correct
    header pass through unchanged.

    Pure ASGI — safe to wrap anyio-based streaming apps.
    """

    _REQUIRED = "application/json, text/event-stream"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        accept = headers.get("accept", "")

        # Rewrite only when one or both required types are absent.
        if "application/json" not in accept or "text/event-stream" not in accept:
            headers["accept"] = self._REQUIRED

        await self.app(scope, receive, send)
