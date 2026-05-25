"""
Session-response builder shared by the Google and Odoo login flows.

Summary:
    Both Google callback and Odoo login submit need to do the same thing
    on success: either bridge an MCP-client OAuth flow back to its
    redirect URI with an auth code, or just confirm to the human, and
    in both cases set an HttpOnly session cookie. This module owns that
    single shared code path so the two login modules stay slim.

Version: 0.2.0
Execution context: library (imported by oauth_google.py + oauth_odoo.py)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .auth import IdentityClaims
from .oauth_helpers import append_query_params


# Session-cookie max age. 12h matches mint_session_token's TTL so the
# cookie and JWT expire together — no zombie cookies referring to dead JWTs.
SESSION_COOKIE_MAX_AGE = 60 * 60 * 12


def build_session_response(
    request: Request,
    claims: IdentityClaims,
    session_token: str,
    session_cookie_name: str,
) -> Response:
    """Bridge the MCP-client flow (if any) and attach the session cookie.

    Returns a RedirectResponse when an upstream MCP flow is bridged through
    us, or an HTMLResponse confirmation page otherwise. In both cases the
    HttpOnly session cookie is set so future requests pick up auth via
    SessionInjectorMiddleware.
    """
    flow_id = str(request.query_params.get("flow") or "").strip()
    if flow_id:
        # An MCP client (e.g. Claude) initiated this OAuth flow through us.
        # Mint a single-use code bound to that client and redirect back.
        flow = request.app.state.oauth_flow_store.pop(flow_id)
        if not flow:
            return JSONResponse(
                {"error": "OAuth flow expired or invalid"}, status_code=400
            )
        bridged_code = request.app.state.oauth_code_store.create(
            claims=claims,
            client_id=flow.client_id,
            redirect_uri=flow.redirect_uri,
            code_challenge=flow.code_challenge,
            code_challenge_method=flow.code_challenge_method,
        )
        redirect_url = append_query_params(
            flow.redirect_uri, {"code": bridged_code, "state": flow.state}
        )
        response: Response = RedirectResponse(redirect_url, status_code=302)
    else:
        # Direct human sign-in: show a friendly confirmation page.
        response = HTMLResponse(
            "<html><body><h1>Authorized</h1>"
            "<p>You can return to Claude and continue.</p></body></html>"
        )
    # HttpOnly: prevent JS access. Secure: HTTPS-only (nginx terminates TLS).
    # SameSite=lax: standard XSRF mitigation; we do not need 'strict'.
    response.set_cookie(
        session_cookie_name,
        session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE,
        path="/",
    )
    return response
