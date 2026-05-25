"""
Odoo login flow — /authorize/odoo (GET form + POST submit).

Summary:
    Native Odoo login path for environments without Google SSO. Renders
    a small HTML form, then on submit authenticates against Odoo's
    XML-RPC `common.authenticate` and converts the result into our
    IdentityClaims. authenticate_odoo_user() is also imported by
    bearer.py for the headless flow — same code path, same guarantees.

Version: 0.2.0
Execution context: library (imported by oauth.py + bearer.py)
"""

from __future__ import annotations

import xmlrpc.client

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from .auth import AuthError, IdentityClaims
from .oauth_helpers import html_escape, parse_urlencoded_body
from .oauth_session import build_session_response
from .oauth_token import mint_session_token


def odoo_login_form(request: Request, public_url: str, odoo_db_name: str | None) -> HTMLResponse:
    """Render a plain Odoo login form for non-SSO environments."""
    db_field = odoo_db_name or ""
    # Escape the flow_id since it round-trips through a hidden input.
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
    # Validate before touching Odoo — cheap fast-fail.
    if not db_name:
        return JSONResponse(
            {"error": "ODOO_DB_NAME is required for Odoo login"}, status_code=400
        )
    if not login or not password:
        return JSONResponse(
            {"error": "Login and password are required"}, status_code=400
        )

    # authenticate_odoo_user() raises AuthError on bad credentials.
    # We let it propagate to the bridged-flow path below; the shared
    # build_session_response handles MCP-client bridge vs. plain page.
    claims = authenticate_odoo_user(
        odoo_url=odoo_url, db_name=db_name, login=login, password=password
    )
    session_token = mint_session_token(
        claims, public_url=public_url, session_secret=session_secret
    )
    return build_session_response(request, claims, session_token, session_cookie_name)


def authenticate_odoo_user(
    *, odoo_url: str, db_name: str, login: str, password: str
) -> IdentityClaims:
    """Authenticate an Odoo login and convert it into identity claims.

    Shared by:
      - oauth_odoo.odoo_login_submit (browser flow)
      - bearer.issue_token_route (headless flow)
    Keeping this in one place guarantees both flows derive identity from
    the exact same Odoo source of truth.
    """
    # Odoo's XML-RPC common endpoint validates credentials and returns uid.
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
    uid = common.authenticate(db_name, login, password, {})
    if not uid:
        raise AuthError("Invalid Odoo credentials")
    # Load the user record to resolve their canonical login + email.
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
    # subject is namespaced ("odoo:<uid>") so downstream code can tell
    # the identity source apart from a Google-issued one.
    return IdentityClaims(
        subject=f"odoo:{uid}", email=actor, scopes=("crm", "project")
    )
