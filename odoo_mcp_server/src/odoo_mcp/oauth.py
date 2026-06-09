"""
OAuth app composition — mounts the browser + headless auth routes.

Summary:
    This file is the thin assembly layer. All real logic lives in the
    sibling modules:

      oauth_stores.py      OAuthState/Flow/Code dataclasses + stores
      oauth_dcr.py         OAuthClient, OAuthClientStore, /register handler
      oauth_authorize.py   /authorize GET — validates OAuth params, stashes flow
      oauth_middleware.py  SessionInjectorMiddleware (cookie → bearer)
      oauth_helpers.py     base64url, html_escape, urlencode helpers,
                           root landing page
      oauth_token.py       mint_session_token, /token, OAuth metadata
      oauth_google.py      /authorize/google + /oauth/callback
      oauth_odoo.py        /authorize/odoo + authenticate_odoo_user
      oauth_session.py     shared response builder (cookie + bridge)

    The headless bearer routes live in bearer.py and are mounted here so
    every auth-touching path is reachable from a single Starlette app.

    Names re-exported at the bottom preserve back-compat for any
    external imports (server.py imports stores and middleware from here).

Version: 0.3.0
Execution context: library (imported by server.py)
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp

from .auth import IdentityTokenVerifier
from .oauth_authorize import authorize
from .oauth_dcr import register_client
from .oauth_google import authorize_google, callback_google
from .oauth_middleware import AcceptNormalizerMiddleware, SessionInjectorMiddleware
from .oauth_odoo import authenticate_odoo_user, odoo_login_form, odoo_login_submit
from .oauth_stores import OAuthCodeStore, OAuthFlowStore, OAuthStateStore
from .oauth_token import (
    mint_session_token,
    oauth_authorization_server,
    oauth_protected_resource,
    oauth_token,
)


# Re-exports keep the old `from .oauth import …` paths working in
# server.py and anywhere else that imported these names directly.
__all__ = [
    "OAuthCodeStore",
    "OAuthFlowStore",
    "OAuthStateStore",
    "SessionInjectorMiddleware",
    "authenticate_odoo_user",
    "build_oauth_ui_app",
    "mint_session_token",
]


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
    """Build the public MCP app plus the OAuth and headless-bearer routes."""
    # Lazy import: bearer.py imports authenticate_odoo_user from this
    # module's re-exports; importing it at module top would cycle.
    from .bearer import issue_token_route, revoke_route, whoami_route

    # Paths the SessionInjectorMiddleware must NOT touch. Each one either
    # already handles its own auth (OAuth endpoints) or carries its own
    # Authorization header (the /auth/* bearer endpoints).
    public_paths = {
        "/",
        "/authorize",
        "/authorize/google",
        "/authorize/odoo",
        "/register",
        "/token",
        "/oauth/callback",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/sse",
        "/.well-known/oauth-authorization-server",
        "/auth/issue-token",
        "/auth/revoke",
        "/auth/whoami",
    }

    # Thin route adapters: each one binds the configured values into the
    # underlying handler so the handler stays pure-functional.
    async def authorize_route(request: Request) -> Response:
        return await authorize(request, public_url, google_client_id)

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
        return callback_google(
            request, verifier, public_url, session_secret, session_cookie_name
        )

    async def oauth_protected_resource_route(request: Request) -> JSONResponse:
        return oauth_protected_resource(request, public_url, resource_url, google_client_id)

    async def oauth_authorization_server_route(request: Request) -> JSONResponse:
        return oauth_authorization_server(request, public_url)

    async def oauth_token_route(request: Request) -> JSONResponse:
        return await oauth_token(request, public_url, session_secret)

    # FastMCP's streamable_http_app() requires its lifespan to run so
    # the StreamableHTTPSessionManager's task group is initialized.
    # Mounted apps do NOT inherit lifespan events, so we forward the
    # mounted MCP app's lifespan onto the outer Starlette app here.
    # Without this, every POST to the MCP endpoint raises:
    #     RuntimeError: Task group is not initialized. Make sure to use run().
    # NOTE: Starlette stores the lifespan on `router.lifespan_context`,
    # not on the app itself. Reading `mcp_app.lifespan` returns None
    # (silent miss) which is what bit the first attempt.
    mcp_lifespan = getattr(
        getattr(mcp_app, "router", None), "lifespan_context", None
    )
    app = Starlette(
        lifespan=mcp_lifespan,
        routes=[
            Route("/", endpoint=authorize_route, methods=["GET"]),
            Route("/authorize", endpoint=authorize_route, methods=["GET"]),
            Route("/authorize/google", endpoint=authorize_google_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_form_route, methods=["GET"]),
            Route("/authorize/odoo", endpoint=odoo_login_submit_route, methods=["POST"]),
            Route("/token", endpoint=oauth_token_route, methods=["POST"]),
            Route("/oauth/callback", endpoint=callback_google_route, methods=["GET"]),
            # RFC 7591 Dynamic Client Registration.
            Route("/register", endpoint=register_client, methods=["POST"]),
            # OAuth discovery metadata.
            Route("/.well-known/oauth-protected-resource", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource/sse", endpoint=oauth_protected_resource_route, methods=["GET"]),
            Route("/.well-known/oauth-authorization-server", endpoint=oauth_authorization_server_route, methods=["GET"]),
            # Headless bearer flow.
            Route("/auth/issue-token", endpoint=issue_token_route, methods=["POST"]),
            Route("/auth/revoke", endpoint=revoke_route, methods=["POST"]),
            Route("/auth/whoami", endpoint=whoami_route, methods=["GET"]),
            # MCP SSE app last so /sse and friends are reachable.
            Mount("/", app=mcp_app),
        ]
    )
    app.add_middleware(
        SessionInjectorMiddleware,
        cookie_name=session_cookie_name,
        public_paths=public_paths,
    )
    # AcceptNormalizerMiddleware is added LAST so it wraps outermost and
    # runs FIRST on every incoming request — before SessionInjector and
    # before the MCP handler — rewriting Accept: */* to the two required
    # MIME types before FastMCP's Accept validation fires.
    app.add_middleware(AcceptNormalizerMiddleware)
    return app
