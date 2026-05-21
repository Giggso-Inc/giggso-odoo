from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import xmlrpc.client
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import jwt
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from .auth import AuthError, IdentityClaims, IdentityTokenVerifier


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class OAuthState:
    code_verifier: str
    created_at: int


class OAuthStateStore:
    """In-memory state store for short-lived login handshakes."""

    def __init__(self) -> None:
        self._states: dict[str, OAuthState] = {}

    def create(self, code_verifier: str) -> str:
        state = secrets.token_urlsafe(32)
        self._states[state] = OAuthState(code_verifier=code_verifier, created_at=int(time.time()))
        return state

    def pop(self, state: str, max_age_seconds: int = 600) -> OAuthState | None:
        item = self._states.pop(state, None)
        if not item:
            return None
        if int(time.time()) - item.created_at > max_age_seconds:
            return None
        return item


class SessionInjectorMiddleware(BaseHTTPMiddleware):
    """Inject a signed session token from a cookie into the bearer auth header."""

    def __init__(self, app: ASGIApp, cookie_name: str, public_paths: set[str]) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        self.public_paths = public_paths

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        if request.url.path in self.public_paths:
            return await call_next(request)
        if request.headers.get("authorization"):
            return await call_next(request)
        cookie_token = request.cookies.get(self.cookie_name)
        if cookie_token:
            headers = MutableHeaders(scope=request.scope)
            headers["authorization"] = f"Bearer {cookie_token}"
        return await call_next(request)


def build_oauth_ui_app(
    *,
    mcp_app: ASGIApp,
    verifier: IdentityTokenVerifier,
    odoo_url: str,
    odoo_db_name: str | None,
    public_url: str,
    resource_url: str,
    google_client_id: str | None,
    session_secret: str,
    session_cookie_name: str = "odoo_mcp_session",
) -> ASGIApp:
    """Build the public MCP app plus Google OAuth login flow."""
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    public_paths = {
        "/",
        "/authorize",
        "/authorize/odoo",
        "/oauth/callback",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/sse",
    }

    async def authorize_google_route(request: Request) -> Response:
        return authorize_google(request, public_url, google_client_id)

    async def odoo_login_form_route(request: Request) -> HTMLResponse:
        return odoo_login_form(request, public_url, odoo_db_name)

    async def odoo_login_submit_route(request: Request) -> Response:
        return await odoo_login_submit(
            request,
            public_url=public_url,
            session_secret=session_secret,
            session_cookie_name=session_cookie_name,
            odoo_url=odoo_url,
            odoo_db_name=odoo_db_name,
        )

    async def callback_google_route(request: Request) -> Response:
        return callback_google(request, verifier, public_url, session_secret, session_cookie_name)

    async def oauth_protected_resource_route(request: Request) -> JSONResponse:
        return oauth_protected_resource(request, public_url, resource_url, google_client_id)

    app = Starlette(
        routes=[
            Route("/", endpoint=lambda request: root_page(request, public_url), methods=["GET"]),
            Route("/authorize", endpoint=authorize_google_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_form_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_submit_route, methods=["POST"]),
            Route("/oauth/callback", endpoint=callback_google_route, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource/sse", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Mount("/", app=mcp_app),
        ]
    )
    app.add_middleware(SessionInjectorMiddleware, cookie_name=session_cookie_name, public_paths=public_paths)
    return app


def root_page(request: Request, public_url: str) -> HTMLResponse:
    """Render a small landing page with the authorize link."""
    google_url = f"{public_url}/authorize"
    odoo_url = f"{public_url}/authorize/odoo"
    html = f"""
    <html>
      <body>
        <h1>Odoo MCP</h1>
        <p><a href="{google_url}">Sign in with Google</a></p>
        <p><a href="{odoo_url}">Sign in with Odoo</a></p>
        <p>After authorization, continue back to your MCP client.</p>
      </body>
    </html>
    """
    return HTMLResponse(html)


def authorize_google(request: Request, public_url: str, google_client_id: str | None) -> Response:
    """Start Google OAuth with PKCE."""
    if not google_client_id:
        return JSONResponse({"error": "ODOO_MCP_GOOGLE_CLIENT_ID is required"}, status_code=500)
    store = request.app.state.oauth_state_store
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
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", status_code=302)


def odoo_login_form(request: Request, public_url: str, odoo_db_name: str | None) -> HTMLResponse:
    """Render a plain Odoo login form for non-SSO environments."""
    db_field = odoo_db_name or ""
    html = f"""
    <html>
      <body>
        <h1>Sign in with Odoo</h1>
        <form method="post" action="{public_url}/authorize/odoo">
          <p><label>Database<br><input name="db" value="{html_escape(db_field)}" /></label></p>
          <p><label>Login<br><input name="login" /></label></p>
          <p><label>Password<br><input name="password" type="password" /></label></p>
          <p><button type="submit">Authorize</button></p>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(html)


async def odoo_login_submit(
    request: Request,
    public_url: str,
    session_secret: str,
    session_cookie_name: str,
    odoo_url: str,
    odoo_db_name: str | None,
) -> Response:
    """Authenticate against Odoo directly and mint a local MCP session."""
    form = await request.form()
    login = str(form.get("login") or "").strip()
    password = str(form.get("password") or "")
    db_name = str(form.get("db") or odoo_db_name or "").strip()
    if not db_name:
        return JSONResponse({"error": "ODOO_DB_NAME is required for Odoo login"}, status_code=400)
    if not login or not password:
        return JSONResponse({"error": "Login and password are required"}, status_code=400)

    claims = authenticate_odoo_user(odoo_url=odoo_url, db_name=db_name, login=login, password=password)
    session_token = mint_session_token(claims, public_url=public_url, session_secret=session_secret)
    response = HTMLResponse(
        "<html><body><h1>Authorized</h1><p>You can return to Claude and continue.</p></body></html>"
    )
    response.set_cookie(
        session_cookie_name,
        session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 12,
        path="/",
    )
    return response


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
        return JSONResponse({"error": error, "error_description": query.get("error_description", "")}, status_code=400)
    code = query.get("code")
    state = query.get("state")
    if not code or not state:
        return JSONResponse({"error": "Missing OAuth code or state"}, status_code=400)
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
        claims = verifier.verify_claims(id_token)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)

    session_token = mint_session_token(claims, public_url=public_url, session_secret=session_secret)
    response = HTMLResponse(
        "<html><body><h1>Authorized</h1><p>You can return to Claude and continue.</p></body></html>"
    )
    response.set_cookie(
        session_cookie_name,
        session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 12,
        path="/",
    )
    return response


def oauth_protected_resource(
    request: Request,
    public_url: str,
    resource_url: str,
    google_client_id: str | None,
) -> JSONResponse:
    """Expose protected-resource metadata for OAuth-aware MCP clients."""
    authorization_servers = list(dict.fromkeys([public_url, request.app.state.identity_issuer or public_url]))
    data = {
        "resource": resource_url,
        "authorization_servers": authorization_servers,
        "bearer_methods_supported": ["header", "cookie"],
        "resource_documentation": f"{public_url}/",
        "scopes_supported": ["openid", "email", "profile"],
    }
    if google_client_id:
        data["client_id_hint"] = google_client_id
    return JSONResponse(data)


def exchange_google_code(*, code: str, code_verifier: str, client_id: str | None, redirect_uri: str) -> dict[str, Any]:
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
    request_obj = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=30) as response:
        return json.loads(response.read())


def authenticate_odoo_user(*, odoo_url: str, db_name: str, login: str, password: str) -> IdentityClaims:
    """Authenticate an Odoo login and convert it into identity claims."""
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
    uid = common.authenticate(db_name, login, password, {})
    if not uid:
        raise AuthError("Invalid Odoo credentials")
    models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
    user_rows = models.execute_kw(
        db_name,
        uid,
        password,
        "res.users",
        "read",
        [[uid]],
        {"fields": ["login", "email"]},
    )
    if not user_rows:
        raise AuthError("Unable to load Odoo user record")
    user = user_rows[0]
    actor = str(user.get("login") or user.get("email") or login).strip()
    if not actor:
        raise AuthError("Odoo user record does not include a login or email")
    return IdentityClaims(subject=f"odoo:{uid}", email=actor, scopes=("crm", "project"))


def mint_session_token(claims: IdentityClaims, *, public_url: str, session_secret: str) -> str:
    """Mint a short-lived MCP session token from verified OIDC claims."""
    payload = {
        "sub": claims.subject,
        "email": claims.email,
        "scope": " ".join(claims.scopes),
        "iss": public_url,
        "aud": public_url,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 12,
        "typ": "odoo-mcp-session",
    }
    return jwt.encode(payload, session_secret, algorithm="HS256")


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
