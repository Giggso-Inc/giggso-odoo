"""
JWT minting + RFC 6749 /token + OAuth metadata endpoints.

Summary:
    The "token plumbing" half of the OAuth flow:
      - mint_session_token(): 12h HS256 JWT with typ=odoo-mcp-session
      - oauth_token(): /token endpoint, validates PKCE, swaps code → JWT
      - oauth_authorization_server(): /.well-known/oauth-authorization-server
      - oauth_protected_resource(): /.well-known/oauth-protected-resource
    Kept together because they all share the same secret + claim shape.

Version: 0.3.0
Execution context: library (imported by oauth.py)
"""

from __future__ import annotations

import hashlib
import hmac
import time

import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import IdentityClaims
from .oauth_helpers import base64url_encode, parse_urlencoded_body


# 12 hours. Browser-flow tokens are short-lived because users can
# re-authorize cheaply. Headless tokens (bearer.py) use 90 days instead.
SESSION_TOKEN_TTL_SECONDS = 60 * 60 * 12


def mint_session_token(claims: IdentityClaims, *, public_url: str, session_secret: str) -> str:
    """Mint a short-lived MCP session token from verified OIDC claims.

    Shape matches the headless bearer flow (bearer_store.mint_long_token)
    so IdentityTokenVerifier accepts both with one code path.
    """
    now = int(time.time())
    payload = {
        "sub": claims.subject,
        "email": claims.email,
        "scope": " ".join(claims.scopes),
        "iss": public_url,
        "aud": public_url,
        "iat": now,
        "exp": now + SESSION_TOKEN_TTL_SECONDS,
        "typ": "odoo-mcp-session",
    }
    return jwt.encode(payload, session_secret, algorithm="HS256")


def oauth_authorization_server(request: Request, public_url: str) -> JSONResponse:
    """Expose OAuth authorization server metadata for MCP clients."""
    # Public clients (Claude, etc.) authenticate with PKCE only;
    # we never accept a client_secret.
    data = {
        "issuer": public_url,
        "authorization_endpoint": f"{public_url}/authorize",
        "token_endpoint": f"{public_url}/token",
        # registration_endpoint advertises RFC 7591 DCR so Claude Desktop
        # can self-register on first connect without any server-side config.
        "registration_endpoint": f"{public_url}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["openid", "email", "profile"],
        "resource_documentation": f"{public_url}/",
    }
    return JSONResponse(data)


def oauth_protected_resource(
    request: Request,
    public_url: str,
    resource_url: str,
    google_client_id: str | None,
) -> JSONResponse:
    """Expose protected-resource metadata for OAuth-aware MCP clients."""
    data = {
        "resource": resource_url,
        "authorization_servers": [public_url],
        # Cookie listed alongside header so browser clients can advertise
        # their session-cookie capability; bearer-flow clients ignore it.
        "bearer_methods_supported": ["header", "cookie"],
        "resource_documentation": f"{public_url}/",
        "scopes_supported": ["openid", "email", "profile"],
    }
    if google_client_id:
        data["client_id_hint"] = google_client_id
    return JSONResponse(data)


async def oauth_token(request: Request, public_url: str, session_secret: str) -> JSONResponse:
    """Exchange an authorization code for a bearer token (RFC 6749 §4.1.3)."""
    form = parse_urlencoded_body(await request.body())
    grant_type = str(form.get("grant_type") or "")
    code = str(form.get("code") or "")
    redirect_uri = str(form.get("redirect_uri") or "")
    code_verifier = str(form.get("code_verifier") or "")
    client_id = str(form.get("client_id") or "")
    # We only support authorization_code; refresh_token would need its
    # own store and revocation strategy (Cycle 3).
    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    if not code or not redirect_uri or not code_verifier or not client_id:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    # Single-use: pop() removes the entry so a stolen code can't be replayed.
    code_item = request.app.state.oauth_code_store.pop(code)
    if not code_item:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "code expired or invalid"},
            status_code=400,
        )
    # Bind the code to the same client and redirect_uri it was issued for.
    if code_item.client_id != client_id:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "client mismatch"},
            status_code=400,
        )
    if code_item.redirect_uri != redirect_uri:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "redirect URI mismatch"},
            status_code=400,
        )
    if code_item.code_challenge_method != "S256":
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "unsupported PKCE method"},
            status_code=400,
        )
    # Constant-time compare prevents PKCE-challenge timing leaks.
    expected_challenge = base64url_encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
    if not hmac.compare_digest(expected_challenge, code_item.code_challenge):
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "PKCE verification failed"},
            status_code=400,
        )

    access_token = mint_session_token(
        code_item.claims, public_url=public_url, session_secret=session_secret
    )
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": SESSION_TOKEN_TTL_SECONDS,
            "scope": " ".join(code_item.claims.scopes),
        }
    )
