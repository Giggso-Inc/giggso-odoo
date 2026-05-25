"""
Headless bearer-token route handlers for Odoo MCP.

Summary:
    Three HTTP endpoints used by clients that cannot drive a browser-based
    OAuth flow (Claude Desktop, custom chatbots, scripts):

      POST /auth/issue-token   -> authenticate Odoo login+password,
                                  return a long-lived session JWT
      POST /auth/revoke        -> add the caller's JWT jti to a denylist
      GET  /auth/whoami        -> verify a Bearer token and return identity

    State and helpers live in bearer_store.py to keep this file ≤170 lines
    and easy to review as pure HTTP glue.

Version: 0.2.0
Execution context: library (routes mounted by oauth.build_oauth_ui_app)

Changelog:
    0.2.0 (Cycle 2.1): point authenticate_odoo_user import at the new
        oauth_odoo module after the oauth.py split.
    0.1.0 (Cycle 2):   initial headless bearer flow.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

# Reuse existing auth + session-token machinery; do not duplicate it.
from .auth import AuthError
from .bearer_store import (
    LONG_TOKEN_TTL_SECONDS,
    config_from_app,
    extract_bearer,
    get_store,
    mint_long_token,
    parse_body,
    peek_jti,
)
# authenticate_odoo_user now lives in oauth_odoo (Cycle 2.1 split). The
# old `from .oauth import authenticate_odoo_user` still works via re-export
# but the direct import keeps the dependency graph honest.
from .oauth_odoo import authenticate_odoo_user


# ───────────────────────────────────────────────────────────────────────
# Route: POST /auth/issue-token
# ───────────────────────────────────────────────────────────────────────
async def issue_token_route(request: Request) -> JSONResponse:
    """Exchange Odoo login+password for a long-lived bearer JWT.

    Body (JSON or x-www-form-urlencoded):
        {db?, login, password, label?}
    Falls back to ODOO_DB_NAME when `db` is omitted.
    """
    config = config_from_app(request)
    payload = await parse_body(request)

    # Normalize inputs; treat missing/blank fields as a 400 (not 500).
    login = str(payload.get("login") or "").strip()
    password = str(payload.get("password") or "")
    db_name = str(payload.get("db") or config.odoo_db_name or "").strip()
    label = str(payload.get("label") or "headless-client")

    if not login or not password:
        return JSONResponse(
            {"error": "login and password are required"}, status_code=400
        )
    if not db_name:
        return JSONResponse(
            {"error": "db is required (or set ODOO_DB_NAME)"}, status_code=400
        )

    # Authenticate against Odoo; identical code path as the browser flow,
    # so success here means the same identity guarantees downstream.
    try:
        claims = authenticate_odoo_user(
            odoo_url=config.odoo_url,
            db_name=db_name,
            login=login,
            password=password,
        )
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

    # Mint a long-lived session JWT (90d) with the cookie-flow shape.
    token = mint_long_token(claims, config=config, label=label)
    return JSONResponse(
        {
            "token": token,
            "token_type": "Bearer",
            "expires_in": LONG_TOKEN_TTL_SECONDS,
            "label": label,
            "subject": claims.subject,
            "email": claims.email,
        }
    )


# ───────────────────────────────────────────────────────────────────────
# Route: POST /auth/revoke
# ───────────────────────────────────────────────────────────────────────
async def revoke_route(request: Request) -> JSONResponse:
    """Revoke the bearer token presented in the Authorization header."""
    config = config_from_app(request)
    token = extract_bearer(request)
    if not token:
        return JSONResponse(
            {"error": "Authorization: Bearer <token> required"}, status_code=401
        )

    # Verify before revoking so callers can't deny arbitrary JTIs.
    try:
        claims = config.verifier.verify_claims(token)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

    # Prefer JTI for precise revocation; fall back to subject (denies all
    # tokens for that user) if the token unexpectedly lacks a JTI.
    jti = peek_jti(token) or claims.subject
    get_store(request).revoke(jti)
    return JSONResponse({"revoked": True, "jti": jti})


# ───────────────────────────────────────────────────────────────────────
# Route: GET /auth/whoami
# ───────────────────────────────────────────────────────────────────────
async def whoami_route(request: Request) -> JSONResponse:
    """Verify the bearer token and echo the resolved identity.

    Doubles as a smoke-test endpoint for Claude Desktop setup so the
    user can confirm their token works before invoking any MCP tool.
    """
    config = config_from_app(request)
    token = extract_bearer(request)
    if not token:
        return JSONResponse(
            {"error": "Authorization: Bearer <token> required"}, status_code=401
        )
    try:
        claims = config.verifier.verify_claims(token)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

    # Enforce revocation here so /whoami is the canonical token health check.
    jti = peek_jti(token)
    if jti and get_store(request).is_revoked(jti):
        return JSONResponse({"error": "token revoked"}, status_code=401)

    return JSONResponse(
        {
            "subject": claims.subject,
            "email": claims.email,
            "scopes": list(claims.scopes),
        }
    )
