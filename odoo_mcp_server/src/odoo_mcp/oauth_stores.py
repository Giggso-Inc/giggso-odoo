"""
In-memory stores for the browser OAuth flow.

Summary:
    Holds the three short-lived stores used during a browser-based OAuth
    handshake: PKCE state, authorization-flow context, and authorization
    codes. All three are in-memory and expire after 600 seconds by
    default. Persistence is deferred to Cycle 3 (Postgres-backed).
    OAuthClientStore (RFC 7591 DCR) lives in oauth_dcr.py.

Version: 0.3.0
Execution context: library (imported by oauth.py + server.py)
"""

from __future__ import annotations

# Stdlib only — these stores are deliberately stateless infrastructure.
import secrets
import time
from dataclasses import dataclass

from .auth import IdentityClaims


# ── Records ─────────────────────────────────────────────────────────────
# Frozen dataclasses so handler code cannot mutate stored entries by
# accident. created_at is unix epoch seconds; max_age defaults to 10 min.

@dataclass(frozen=True)
class OAuthState:
    code_verifier: str
    created_at: int


@dataclass(frozen=True)
class OAuthFlow:
    client_id: str
    redirect_uri: str
    state: str
    code_challenge: str
    code_challenge_method: str
    created_at: int


@dataclass(frozen=True)
class OAuthCode:
    claims: IdentityClaims
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    created_at: int


# ── Stores ──────────────────────────────────────────────────────────────
# Each store does the same thing: create() returns a fresh token, pop()
# atomically removes + returns the entry (or None if expired/missing).
# pop() is intentionally single-use to prevent replay.

class OAuthStateStore:
    """Short-lived PKCE state between /authorize/google and /oauth/callback."""

    def __init__(self) -> None:
        self._states: dict[str, OAuthState] = {}

    def create(self, code_verifier: str) -> str:
        # 32 bytes urlsafe → ~43 chars; enough entropy for state.
        state = secrets.token_urlsafe(32)
        self._states[state] = OAuthState(
            code_verifier=code_verifier,
            created_at=int(time.time()),
        )
        return state

    def pop(self, state: str, max_age_seconds: int = 600) -> OAuthState | None:
        item = self._states.pop(state, None)
        if not item:
            return None
        # Expired entries are silently dropped rather than raised — the
        # caller already knows what to do (400 invalid_state).
        if int(time.time()) - item.created_at > max_age_seconds:
            return None
        return item


class OAuthFlowStore:
    """Tracks an OAuth authorization request from the MCP client."""

    def __init__(self) -> None:
        self._flows: dict[str, OAuthFlow] = {}

    def create(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        flow_id = secrets.token_urlsafe(24)
        self._flows[flow_id] = OAuthFlow(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            created_at=int(time.time()),
        )
        return flow_id

    def pop(self, flow_id: str, max_age_seconds: int = 600) -> OAuthFlow | None:
        item = self._flows.pop(flow_id, None)
        if not item:
            return None
        if int(time.time()) - item.created_at > max_age_seconds:
            return None
        return item


class OAuthCodeStore:
    """Issues + redeems short-lived authorization codes (single-use)."""

    def __init__(self) -> None:
        self._codes: dict[str, OAuthCode] = {}

    def create(
        self,
        *,
        claims: IdentityClaims,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._codes[code] = OAuthCode(
            claims=claims,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            created_at=int(time.time()),
        )
        return code

    def pop(self, code: str, max_age_seconds: int = 600) -> OAuthCode | None:
        item = self._codes.pop(code, None)
        if not item:
            return None
        if int(time.time()) - item.created_at > max_age_seconds:
            return None
        return item
