"""
RFC 7591 Dynamic Client Registration — /register endpoint.

Summary:
    Implements the /register POST endpoint and the OAuthClientStore that
    backs it. Public clients only (PKCE mandatory, no client_secret).
    Redirect-URI policy is permissive by design: localhost:* and the
    claude-desktop:// custom scheme are both valid so DCR works for any
    Claude Desktop install without server-side config changes.

Version: 1.0.0
Execution context: library (imported by oauth.py + server.py)
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse


# ── Client record ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OAuthClient:
    """A dynamically-registered OAuth public client (RFC 7591).

    No client_secret is ever issued — PKCE is the only client
    authentication mechanism we support, by design.
    redirect_uris stored as tuple because frozen dataclass needs hashable.
    """
    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    created_at: int


# ── Store ────────────────────────────────────────────────────────────────

class OAuthClientStore:
    """In-memory RFC 7591 Dynamic Client Registration store.

    Clients registered here persist for the process lifetime (no TTL).
    A future Cycle 3 migration will swap this for a Postgres-backed
    implementation using the same public interface.
    """

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClient] = {}

    def register(self, *, client_name: str, redirect_uris: list[str]) -> OAuthClient:
        """Register a new public client and return the record."""
        # 24 bytes → ~32 URL-safe chars; unique within this process.
        client_id = secrets.token_urlsafe(24)
        client = OAuthClient(
            client_id=client_id,
            client_name=client_name,
            redirect_uris=tuple(redirect_uris),
            created_at=int(time.time()),
        )
        self._clients[client_id] = client
        return client

    def get(self, client_id: str) -> OAuthClient | None:
        """Look up a client by ID; returns None if unknown."""
        return self._clients.get(client_id)


# ── Redirect-URI validation ───────────────────────────────────────────────

def _is_allowed_redirect_uri(uri: str) -> bool:
    """Validate a redirect URI for a public DCR client.

    Permissive by design: Claude Desktop registers a random localhost port
    each time it starts, so we cannot validate against a fixed allowlist.
    We accept:
      - http://localhost:* (Claude Desktop callback on any local port)
      - http://127.0.0.1:* (same, numeric form)
      - claude-desktop://* (Claude's custom URI scheme on some platforms)
    We reject everything else (e.g. remote HTTPS redirect URIs would allow
    auth code interception by a remote party).
    """
    # Allow localhost variants for the standard OAuth loopback flow.
    if uri.startswith("http://localhost:") or uri.startswith("http://127.0.0.1:"):
        return True
    # Allow the Claude Desktop custom scheme (app-owned, not interceptable).
    if uri.startswith("claude-desktop://"):
        return True
    return False


# ── Route handler ─────────────────────────────────────────────────────────

async def register_client(request: Request) -> JSONResponse:
    """Handle POST /register — RFC 7591 Dynamic Client Registration.

    Accepts JSON body with client_name and redirect_uris. Returns a
    client_id immediately (no client_secret — public clients only).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "JSON body required"},
            status_code=400,
        )

    client_name = str(body.get("client_name") or "").strip()
    redirect_uris = body.get("redirect_uris")

    if not client_name:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "client_name required"},
            status_code=400,
        )
    if not redirect_uris or not isinstance(redirect_uris, list):
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "redirect_uris must be a list"},
            status_code=400,
        )

    # Reject any URI that doesn't match our allowed schemes — prevents a
    # malicious registrant from setting up a remote redirect target.
    bad = [u for u in redirect_uris if not _is_allowed_redirect_uri(str(u))]
    if bad:
        return JSONResponse(
            {
                "error": "invalid_redirect_uri",
                "error_description": f"Disallowed redirect URI(s): {bad}",
            },
            status_code=400,
        )

    client = request.app.state.oauth_client_store.register(
        client_name=client_name,
        redirect_uris=[str(u) for u in redirect_uris],
    )
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_name": client.client_name,
            "redirect_uris": list(client.redirect_uris),
            "client_id_issued_at": client.created_at,
            # RFC 7591 §3.2.1: omitting client_secret signals public client.
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        },
        status_code=201,
    )
