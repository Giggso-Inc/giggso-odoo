"""
/authorize GET endpoint — validates OAuth params and creates a flow.

Summary:
    Handles the RFC 6749 §4.1.1 authorization request. When OAuth params
    are present it validates them, looks up the registered client, stashes
    a flow record, and renders the landing page with the flow_id embedded
    so the chosen sign-in method can finish the code-grant redirect.
    Direct browser visits (no OAuth params) skip validation and render
    the plain landing page.

Version: 1.0.0
Execution context: library (imported by oauth.py)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from .oauth_helpers import root_page


async def authorize(
    request: Request,
    public_url: str,
    google_client_id: str | None,
) -> HTMLResponse | JSONResponse:
    """Entry-point for RFC 6749 §4.1.1 authorization requests.

    Two modes:
      1. Plain browser visit (no OAuth params) → render landing page.
      2. OAuth authorization request → validate, stash flow, render
         landing page with flow_id so login can complete the redirect.
    """
    params = request.query_params
    response_type = params.get("response_type", "")
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "")
    state = params.get("state", "")

    # Plain browser visit — no OAuth params means a human typed the URL
    # directly. Show the landing page without creating a flow record.
    if not any([response_type, client_id, redirect_uri, code_challenge]):
        return root_page(request, public_url, google_client_id)

    # Minimum required params per RFC 6749 §4.1.1 + PKCE RFC 7636.
    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)
    if not client_id or not redirect_uri or not code_challenge:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    # We only support S256; plain (no challenge method) defaults to S256.
    if code_challenge_method and code_challenge_method != "S256":
        return JSONResponse(
            {"error": "invalid_request", "error_description": "only S256 supported"},
            status_code=400,
        )

    # Verify the client was registered via DCR. Unknown client_ids are
    # rejected here to prevent this endpoint from acting as an open
    # redirector for arbitrary redirect_uris.
    client = request.app.state.oauth_client_store.get(client_id)
    if not client:
        return JSONResponse(
            {"error": "invalid_client", "error_description": "unknown client_id"},
            status_code=400,
        )

    # The redirect_uri must exactly match one the client registered —
    # even a trailing-slash difference is rejected per RFC 6749 §3.1.2.
    if redirect_uri not in client.redirect_uris:
        return JSONResponse(
            {"error": "invalid_redirect_uri", "error_description": "redirect_uri not registered"},
            status_code=400,
        )

    flow_id = request.app.state.oauth_flow_store.create(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge,
        # Default to S256 when the client omits the method (PKCE RFC §4.3).
        code_challenge_method=code_challenge_method or "S256",
    )
    # Embed the flow_id in the landing page so the user's chosen sign-in
    # method carries it through to the POST handler.
    return root_page(request, public_url, google_client_id, flow_id=flow_id)
