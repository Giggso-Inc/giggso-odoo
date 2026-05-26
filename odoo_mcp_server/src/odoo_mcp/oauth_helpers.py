"""
Pure helper functions shared across the OAuth modules.

Summary:
    No state, no I/O — just URL/HTML/base64 plumbing plus the small
    landing-page renderer. Kept in one place so the auth modules can
    import without pulling in the heavyweight Google/Odoo paths.

Version: 0.3.0
Execution context: library (imported by oauth_*.py and oauth.py)
"""

from __future__ import annotations

import base64
import urllib.parse

from starlette.requests import Request
from starlette.responses import HTMLResponse


def base64url_encode(value: bytes) -> str:
    """URL-safe base64 without padding (RFC 7515 §2)."""
    # rstrip('=') because JWTs and PKCE challenges use unpadded form.
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def html_escape(value: str) -> str:
    """Minimal HTML escape sufficient for our login form fields."""
    # We do not use html.escape() because we also need to escape single
    # quotes for HTML-attribute contexts; the stdlib version does not.
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def parse_urlencoded_body(body: bytes) -> dict[str, str]:
    """Parse an x-www-form-urlencoded request body into a flat dictionary."""
    # parse_qs returns lists; collapse to the last value per key so
    # callers can treat the result as a flat dict.
    raw = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in raw.items() if values}


def append_query_params(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL, preserving existing ones."""
    # urlsplit → modify → urlunsplit is the only safe way to round-trip
    # a URL without losing fragment or accidentally re-encoding the path.
    parsed = urllib.parse.urlsplit(url)
    existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    merged = existing + list(params.items())
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(merged)))


def root_page(
    request: Request,
    public_url: str,
    google_client_id: str | None = None,
    flow_id: str = "",
) -> HTMLResponse:
    """Render the small landing page with the available authorize links.

    flow_id is forwarded as a query param so /authorize/odoo can pick up
    the OAuth context after the user chooses their sign-in method. Without
    it the login form has no way to know which client initiated the flow.
    """
    # Carry flow_id into whichever sign-in link the user clicks.
    flow_suffix = f"?flow={html_escape(flow_id)}" if flow_id else ""
    odoo_url = f"{public_url}/authorize/odoo{flow_suffix}"
    # Only show the Google link when a client ID is configured; otherwise
    # users would hit a runtime error after clicking.
    google_link = (
        f'<p><a href="{public_url}/authorize/google{flow_suffix}">Sign in with Google</a></p>'
        if google_client_id
        else ""
    )
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
