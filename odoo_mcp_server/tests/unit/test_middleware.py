"""Unit tests for SessionInjectorMiddleware and AcceptNormalizerMiddleware.

Both classes are pure ASGI callables — no Odoo, no server required.
Tests build minimal ASGI scopes, call the middleware, and inspect the
mutated scope headers.
"""
from __future__ import annotations

import asyncio

import pytest

from odoo_mcp.oauth_middleware import AcceptNormalizerMiddleware, SessionInjectorMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_http_scope(headers: dict[str, str], path: str = "/mcp") -> dict:
    """Build a minimal ASGI HTTP scope with the given headers."""
    return {
        "type": "http",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }


def make_lifespan_scope() -> dict:
    return {"type": "lifespan"}


async def noop_app(scope, receive, send) -> None:
    pass


def header_dict(scope: dict) -> dict[str, str]:
    """Extract ASGI scope headers as a lower-cased string dict."""
    return {k.decode(): v.decode() for k, v in scope["headers"]}


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# AcceptNormalizerMiddleware
# ---------------------------------------------------------------------------

class TestAcceptNormalizerMiddleware:
    def _mw(self) -> AcceptNormalizerMiddleware:
        return AcceptNormalizerMiddleware(noop_app)

    def test_no_accept_header_sets_both_required_types(self):
        scope = make_http_scope({})
        run(self._mw()(scope, None, None))
        accept = header_dict(scope)["accept"]
        assert "application/json" in accept
        assert "text/event-stream" in accept

    def test_wildcard_accept_appends_both_types_and_preserves_wildcard(self):
        scope = make_http_scope({"Accept": "*/*"})
        run(self._mw()(scope, None, None))
        accept = header_dict(scope)["accept"]
        assert "*/*" in accept
        assert "application/json" in accept
        assert "text/event-stream" in accept

    def test_missing_sse_only_appends_sse_and_keeps_json(self):
        scope = make_http_scope({"Accept": "application/json, text/html"})
        run(self._mw()(scope, None, None))
        accept = header_dict(scope)["accept"]
        assert "text/event-stream" in accept
        assert "application/json" in accept
        assert "text/html" in accept

    def test_missing_json_only_appends_json_and_keeps_sse(self):
        scope = make_http_scope({"Accept": "text/event-stream"})
        run(self._mw()(scope, None, None))
        accept = header_dict(scope)["accept"]
        assert "application/json" in accept
        assert "text/event-stream" in accept

    def test_both_present_header_unchanged(self):
        original = "application/json, text/event-stream"
        scope = make_http_scope({"Accept": original})
        run(self._mw()(scope, None, None))
        assert header_dict(scope)["accept"] == original

    def test_both_present_with_extras_header_unchanged(self):
        original = "text/html, application/json, text/event-stream"
        scope = make_http_scope({"Accept": original})
        run(self._mw()(scope, None, None))
        assert header_dict(scope)["accept"] == original

    def test_non_http_scope_passes_through_unmodified(self):
        scope = make_lifespan_scope()
        run(self._mw()(scope, None, None))
        assert "headers" not in scope


# ---------------------------------------------------------------------------
# SessionInjectorMiddleware
# ---------------------------------------------------------------------------

class TestSessionInjectorMiddleware:
    _PUBLIC = {"/auth/login", "/auth/callback", "/.well-known/oauth-authorization-server"}

    def _mw(self) -> SessionInjectorMiddleware:
        return SessionInjectorMiddleware(
            noop_app,
            cookie_name="mcp_session",
            public_paths=self._PUBLIC,
        )

    def test_injects_cookie_as_bearer_token(self):
        scope = make_http_scope({"Cookie": "mcp_session=tok123"})
        run(self._mw()(scope, None, None))
        assert header_dict(scope)["authorization"] == "Bearer tok123"

    def test_no_cookie_no_auth_header_added(self):
        scope = make_http_scope({})
        run(self._mw()(scope, None, None))
        assert "authorization" not in header_dict(scope)

    def test_existing_authorization_not_overwritten(self):
        scope = make_http_scope({
            "Authorization": "Bearer original-token",
            "Cookie": "mcp_session=cookie-token",
        })
        run(self._mw()(scope, None, None))
        assert header_dict(scope)["authorization"] == "Bearer original-token"

    def test_public_path_skips_cookie_injection(self):
        scope = make_http_scope({"Cookie": "mcp_session=tok123"}, path="/auth/login")
        run(self._mw()(scope, None, None))
        assert "authorization" not in header_dict(scope)

    def test_wrong_cookie_name_ignored(self):
        scope = make_http_scope({"Cookie": "other_cookie=tok123"})
        run(self._mw()(scope, None, None))
        assert "authorization" not in header_dict(scope)

    def test_multiple_cookies_picks_correct_one(self):
        scope = make_http_scope({"Cookie": "session_id=abc; mcp_session=real-token; lang=en"})
        run(self._mw()(scope, None, None))
        assert header_dict(scope)["authorization"] == "Bearer real-token"

    def test_non_http_scope_passes_through(self):
        scope = make_lifespan_scope()
        run(self._mw()(scope, None, None))
        assert "headers" not in scope
