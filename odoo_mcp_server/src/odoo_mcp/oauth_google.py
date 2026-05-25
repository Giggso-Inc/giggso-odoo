"""
Google OAuth flow — /authorize/google + /oauth/callback.

Summary:
    Implements the Google leg of the browser-based sign-in:
      - authorize_google(): builds the Google OAuth URL with PKCE
      - exchange_google_code(): swaps the auth code for tokens at Google
      - callback_google(): verifies the ID token, mints our session JWT,
        and (optionally) bridges the inbound MCP-client OAuth flow back
        to its redirect URI.

Version: 0.2.0
Execution context: library (imported by oauth.py)
"""

from __future__ import annotations

import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from .auth import AuthError, IdentityTokenVerifier
from .oauth_helpers import base64url_encode
from .oauth_session import build_session_response
from .oauth_token import mint_session_token


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def authorize_google(request: Request, public_url: str, google_client_id: str | None) -> Response:
    """Start Google OAuth with PKCE."""
    if not google_client_id:
        # Fail fast and visibly rather than redirecting to a broken Google URL.
        return JSONResponse(
            {"error": "ODOO_MCP_GOOGLE_CLIENT_ID is required"}, status_code=500
        )
    # If the caller is bridging an MCP-client flow, preserve it so we can
    # complete the redirect after Google returns.
    flow_id = str(request.query_params.get("flow") or "").strip()
    flow = request.app.state.oauth_flow_store.pop(flow_id) if flow_id else None
    if flow_id and not flow:
        return JSONResponse({"error": "OAuth flow expired or invalid"}, status_code=400)

    store = request.app.state.oauth_state_store
    # PKCE: 64-byte verifier → SHA-256 challenge → urlsafe-b64 (no pad).
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64url_encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
    state = store.create(code_verifier)
    redirect_uri = f"{public_url}/oauth/callback"
    params = {
        "client_id": google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # Always show the account chooser; avoids accidental silent re-auth
        # under the wrong Google identity.
        "prompt": "select_account",
    }
    # Re-store the MCP-client flow so the callback can pop it after Google.
    if flow:
        request.app.state.oauth_flow_store.create(
            client_id=flow.client_id,
            redirect_uri=flow.redirect_uri,
            state=flow.state,
            code_challenge=flow.code_challenge,
            code_challenge_method=flow.code_challenge_method,
        )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", status_code=302)


def exchange_google_code(
    *,
    code: str,
    code_verifier: str,
    client_id: str | None,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange the Google authorization code for tokens using PKCE."""
    if not client_id:
        raise ValueError("ODOO_MCP_GOOGLE_CLIENT_ID is required")
    form = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    # Plain urllib keeps the dependency surface minimal; this code path
    # only ever talks to Google's well-known token endpoint.
    request_obj = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=30) as response:
        return json.loads(response.read())


def callback_google(
    request: Request,
    verifier: IdentityTokenVerifier,
    public_url: str,
    session_secret: str,
    session_cookie_name: str,
) -> Response:
    """Handle Google OAuth callback and mint a short-lived MCP session."""
    query = request.query_params
    error = query.get("error")
    if error:
        return JSONResponse(
            {"error": error, "error_description": query.get("error_description", "")},
            status_code=400,
        )
    code = query.get("code")
    state = query.get("state")
    if not code or not state:
        return JSONResponse({"error": "Missing OAuth code or state"}, status_code=400)
    # State store is single-use; pop() also acts as the replay check.
    state_item = request.app.state.oauth_state_store.pop(state)
    if not state_item:
        return JSONResponse({"error": "OAuth state expired or invalid"}, status_code=400)

    token_response = exchange_google_code(
        code=code,
        code_verifier=state_item.code_verifier,
        client_id=request.app.state.google_client_id,
        redirect_uri=f"{public_url}/oauth/callback",
    )
    id_token = token_response.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        return JSONResponse({"error": "Google did not return an ID token"}, status_code=400)
    try:
        # Verifier checks signature + issuer + audience against JWKS.
        claims = verifier.verify_claims(id_token)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

    # Build the response (bridge or confirmation) + attach the session cookie.
    session_token = mint_session_token(
        claims, public_url=public_url, session_secret=session_secret
    )
    return build_session_response(request, claims, session_token, session_cookie_name)
