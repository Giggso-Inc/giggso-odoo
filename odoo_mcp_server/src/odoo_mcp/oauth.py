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


class OAuthFlowStore:
    """In-memory store for OAuth authorization requests."""

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
    """In-memory store for short-lived authorization codes."""

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
        "/authorize/google",
        "/authorize/odoo",
        "/token",
        "/oauth/callback",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/sse",
        "/.well-known/oauth-authorization-server",
    }

    async def authorize_route(request: Request) -> HTMLResponse:
        return root_page(request, public_url, google_client_id)

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

    async def oauth_authorization_server_route(request: Request) -> JSONResponse:
        return oauth_authorization_server(request, public_url)

    async def oauth_token_route(request: Request) -> JSONResponse:
        return await oauth_token(request, public_url, session_secret)

    app = Starlette(
        routes=[
            Route("/", endpoint=authorize_route, methods=["GET"]),
            Route("/authorize", endpoint=authorize_route, methods=["GET"]),
            Route("/authorize/google", endpoint=authorize_google_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_form_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_submit_route, methods=["POST"]),
            Route("/token", endpoint=oauth_token_route, methods=["POST"]),
            Route("/oauth/callback", endpoint=callback_google_route, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource/sse", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Route("/.well-known/oauth-authorization-server", endpoint=oauth_authorization_server_route, methods=["GET"]),
            Mount("/", app=mcp_app),
        ]
    )
    app.add_middleware(SessionInjectorMiddleware, cookie_name=session_cookie_name, public_paths=public_paths)
    return app


def root_page(request: Request, public_url: str, google_client_id: str | None = None) -> HTMLResponse:
    """Render a small landing page with the authorize link."""
    odoo_url = f"{public_url}/authorize/odoo"
    google_link = f'<p><a href="{public_url}/authorize/google">Sign in with Google</a></p>' if google_client_id else ""
    html = f"""
    <html>
      <body>
        <h1>Odoo MCP</h1>
        <p><a href="{odoo_url}">Sign in with Odoo</a></p>
        {google_link}
        <p>After authorization, continue back to your MCP client.</p>
      </body>
    </html>
    """
    return HTMLResponse(html)


def oauth_authorization_server(request: Request, public_url: str) -> JSONResponse:
    """Expose OAuth authorization server metadata for MCP clients."""
    data = {
        "issuer": public_url,
        "authorization_endpoint": f"{public_url}/authorize",
        "token_endpoint": f"{public_url}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["openid", "email", "profile"],
        "resource_documentation": f"{public_url}/",
    }
    return JSONResponse(data)


def authorize_google(request: Request, public_url: str, google_client_id: str | None) -> Response:
    """Start Google OAuth with PKCE."""
    if not google_client_id:
        return JSONResponse({"error": "ODOO_MCP_GOOGLE_CLIENT_ID is required"}, status_code=500)
    flow_id = str(request.query_params.get("flow") or "").strip()
    flow = request.app.state.oauth_flow_store.pop(flow_id) if flow_id else None
    if flow_id and not flow:
        return JSONResponse({"error": "OAuth flow expired or invalid"}, status_code=400)
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
    if flow:
        request.app.state.oauth_flow_store.create(
            client_id=flow.client_id,
            redirect_uri=flow.redirect_uri,
            state=flow.state,
            code_challenge=flow.code_challenge,
            code_challenge_method=flow.code_challenge_method,
        )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", status_code=302)


def odoo_login_form(request: Request, public_url: str, odoo_db_name: str | None) -> HTMLResponse:
    """Render a plain Odoo login form for non-SSO environments."""
    db_field = odoo_db_name or ""
    flow_id = html_escape(str(request.query_params.get("flow") or ""))
    html = f"""
    <html>
      <body>
        <h1>Sign in with Odoo</h1>
        <form method="post" action="{public_url}/authorize/odoo">
          <input type="hidden" name="flow" value="{flow_id}" />
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
    form = parse_urlencoded_body(await request.body())
    login = str(form.get("login") or "").strip()
    password = str(form.get("password") or "")
    db_name = str(form.get("db") or odoo_db_name or "").strip()
    flow_id = str(form.get("flow") or "").strip()
    if not db_name:
        return JSONResponse({"error": "ODOO_DB_NAME is required for Odoo login"}, status_code=400)
    if not login or not password:
        return JSONResponse({"error": "Login and password are required"}, status_code=400)

    claims = authenticate_odoo_user(odoo_url=odoo_url, db_name=db_name, login=login, password=password)
    if flow_id:
        flow = request.app.state.oauth_flow_store.pop(flow_id)
        if not flow:
            return JSONResponse({"error": "OAuth flow expired or invalid"}, status_code=400)
        code = request.app.state.oauth_code_store.create(
            claims=claims,
            client_id=flow.client_id,
            redirect_uri=flow.redirect_uri,
            code_challenge=flow.code_challenge,
            code_challenge_method=flow.code_challenge_method,
        )
        redirect_url = append_query_params(flow.redirect_uri, {"code": code, "state": flow.state})
        return RedirectResponse(redirect_url, status_code=302)

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

    flow_id = str(request.query_params.get("flow") or "").strip()
    if flow_id:
        flow = request.app.state.oauth_flow_store.pop(flow_id)
        if not flow:
            return JSONResponse({"error": "OAuth flow expired or invalid"}, status_code=400)
        code = request.app.state.oauth_code_store.create(
            claims=claims,
            client_id=flow.client_id,
            redirect_uri=flow.redirect_uri,
            code_challenge=flow.code_challenge,
            code_challenge_method=flow.code_challenge_method,
        )
        redirect_url = append_query_params(flow.redirect_uri, {"code": code, "state": flow.state})
        response = RedirectResponse(redirect_url, status_code=302)
        response.set_cookie(
            session_cookie_name,
            mint_session_token(claims, public_url=public_url, session_secret=session_secret),
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=60 * 60 * 12,
            path="/",
        )
        return response

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
    data = {
        "resource": resource_url,
        "authorization_servers": [public_url],
        "bearer_methods_supported": ["header", "cookie"],
        "resource_documentation": f"{public_url}/",
        "scopes_supported": ["openid", "email", "profile"],
    }
    if google_client_id:
        data["client_id_hint"] = google_client_id
    return JSONResponse(data)


async def oauth_token(request: Request, public_url: str, session_secret: str) -> JSONResponse:
    """Exchange an authorization code for a bearer token."""
    form = parse_urlencoded_body(await request.body())
    grant_type = str(form.get("grant_type") or "")
    code = str(form.get("code") or "")
    redirect_uri = str(form.get("redirect_uri") or "")
    code_verifier = str(form.get("code_verifier") or "")
    client_id = str(form.get("client_id") or "")
    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    if not code or not redirect_uri or not code_verifier or not client_id:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    code_item = request.app.state.oauth_code_store.pop(code)
    if not code_item:
        return JSONResponse({"error": "invalid_grant", "error_description": "code expired or invalid"}, status_code=400)
    if code_item.client_id != client_id:
        return JSONResponse({"error": "invalid_grant", "error_description": "client mismatch"}, status_code=400)
    if code_item.redirect_uri != redirect_uri:
        return JSONResponse({"error": "invalid_grant", "error_description": "redirect URI mismatch"}, status_code=400)
    if code_item.code_challenge_method != "S256":
        return JSONResponse({"error": "invalid_grant", "error_description": "unsupported PKCE method"}, status_code=400)
    expected_challenge = base64url_encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
    if not hmac.compare_digest(expected_challenge, code_item.code_challenge):
        return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

    access_token = mint_session_token(code_item.claims, public_url=public_url, session_secret=session_secret)
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 60 * 60 * 12,
            "scope": " ".join(code_item.claims.scopes),
        }
    )


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


def parse_urlencoded_body(body: bytes) -> dict[str, str]:
    """Parse an x-www-form-urlencoded request body into a flat dictionary."""
    raw = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in raw.items() if values}


def append_query_params(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL."""
    parsed = urllib.parse.urlsplit(url)
    existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    merged = existing + list(params.items())
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(merged)))
