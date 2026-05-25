"""
Bearer-token state + helpers for the headless auth flow.

Summary:
    Holds configuration, the in-memory revocation denylist, body parsing,
    Authorization-header parsing, JTI peek, and the long-lived JWT minter.
    Kept separate from bearer.py so each file stays ≤170 lines and the
    route handlers in bearer.py read as pure HTTP glue.

    The minted JWT uses the same HS256 secret and `typ: odoo-mcp-session`
    as the browser cookie flow in oauth.py, so the existing
    IdentityTokenVerifier accepts it unchanged. No new key material.

Version: 0.2.0
Execution context: library (imported by bearer.py and server.py)

Changelog:
    0.2.0 (Cycle 2.1): no behaviour change; version bumped alongside the
        oauth.py split so the auth-flow files share a coherent version.
    0.1.0 (Cycle 2):   initial headless bearer-token state + minter.
"""

from __future__ import annotations

# Stdlib only — no new runtime dependency surface.
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request

from .auth import IdentityClaims, IdentityTokenVerifier


# Long-token lifetime: 90 days. Matches the v1 plan ("issue once for Claude
# Desktop, rotate quarterly"). Tunable via constructor if needed later.
LONG_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90


@dataclass(frozen=True)
class BearerConfig:
    """Per-app configuration attached to app.state by server.py.

    Kept frozen so route handlers cannot accidentally mutate shared state.
    """

    public_url: str
    session_secret: str
    odoo_url: str
    odoo_db_name: str | None
    verifier: IdentityTokenVerifier


class RevokedTokenStore:
    """In-process JTI denylist. Lost on process restart.

    Acceptable for Cycle 2 because:
      • Tokens still expire at exp; revocation is a fast-path override.
      • Restart = denylist clears = revoked tokens become valid again until
        exp. Documented in docs/clients/claude-desktop.md as a known limit.
    Cycle 3 should move this to Postgres alongside the OAuth stores.
    """

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def revoke(self, jti: str) -> None:
        # Track by JTI so the exact same token string cannot be reused.
        self._revoked.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked


# Module-level fallback store. server.py assigns its own instance to
# app.state.revoked_token_store; get_store() prefers that one.
_DEFAULT_STORE = RevokedTokenStore()


def get_store(request: Request) -> RevokedTokenStore:
    """Return the per-app revocation store, falling back to the module default."""
    return getattr(request.app.state, "revoked_token_store", _DEFAULT_STORE)


def config_from_app(request: Request) -> BearerConfig:
    """Pull the BearerConfig stashed on app.state by server.py."""
    cfg = getattr(request.app.state, "bearer_config", None)
    if cfg is None:
        # Fail loud — misconfiguration, not a request error.
        raise RuntimeError("bearer_config not attached to app.state")
    return cfg


async def parse_body(request: Request) -> dict[str, Any]:
    """Accept JSON or x-www-form-urlencoded so curl + chatbots both work."""
    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    # Prefer JSON when declared; otherwise fall back to form encoding.
    if "application/json" in content_type:
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}
    parsed = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    # parse_qs returns lists; take the last value per key (curl repeat semantics).
    return {key: values[-1] for key, values in parsed.items() if values}


def extract_bearer(request: Request) -> str | None:
    """Pull `Authorization: Bearer <token>` from the request headers."""
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def peek_jti(token: str) -> str | None:
    """Read the JTI claim from a JWT payload without re-verifying signature.

    Safe because the caller has already verified the token via the
    IdentityTokenVerifier; this is just a cheap claim lookup.
    """
    try:
        # Local import keeps the top of the file clean of helper deps.
        from .auth import base64url_decode
        _, payload_b64, _ = token.split(".")
        payload = json.loads(base64url_decode(payload_b64))
        jti = payload.get("jti")
        return str(jti) if jti else None
    except Exception:
        # Malformed token → no JTI; revocation falls back to denying subject.
        return None


def mint_long_token(claims: IdentityClaims, *, config: BearerConfig, label: str) -> str:
    """Mint a 90-day session JWT with the same shape as the cookie flow.

    oauth.mint_session_token() hardcodes a 12h TTL; headless clients like
    Claude Desktop need a longer-lived token. We mint here with identical
    `typ`, algorithm, and secret so IdentityTokenVerifier accepts it as-is.
    """
    # PyJWT is already a hard dependency through oauth.py.
    import jwt

    now = int(time.time())
    payload = {
        "sub": claims.subject,
        "email": claims.email,
        "scope": " ".join(claims.scopes),
        "iss": config.public_url,
        "aud": config.public_url,
        "iat": now,
        "nbf": now,
        "exp": now + LONG_TOKEN_TTL_SECONDS,
        "typ": "odoo-mcp-session",
        # JTI lets us denylist this exact token on /auth/revoke.
        "jti": secrets.token_urlsafe(16),
        # Human-readable label for ops ("claude-desktop-laptop", etc.).
        "label": label,
    }
    return jwt.encode(payload, config.session_secret, algorithm="HS256")
