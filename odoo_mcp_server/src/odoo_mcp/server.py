"""
Odoo MCP server entry point.

Summary:
    Builds the FastMCP server, registers tool modules (admin, crm,
    projects), and either runs the stdio transport directly or hands
    off to run_uvicorn_sse() which mounts the OAuth + headless-bearer
    Starlette app via build_oauth_ui_app(). TLS is optional — when
    cert/key paths are empty, a sidecar (nginx) terminates TLS.

Version: 0.4.1
Execution context: process entry point (CLI `python -m odoo_mcp.server`)

Changelog:
    0.4.1 (Cycle 2.4): override FastMCP streamable_http_path default
        from `/mcp` to `/` so the streamable-http endpoint lives at
        the root URL — marketplace clients configure with bare base
        URL only.
    0.4.0 (Cycle 2.4): pick MCP ASGI app based on transport setting.
        When ODOO_MCP_TRANSPORT=streamable-http, mount
        mcp.streamable_http_app() at root so marketplace clients can
        configure with just the base URL (no /sse suffix). SSE path
        retained for backwards compatibility.
    0.3.0 (Cycle 2.3): decouple bearer/OAuth-UI app from TLS settings.
        Sidecar-terminated TLS deployments (nginx in front of plain
        uvicorn) now also serve /auth/issue-token, /auth/whoami, etc.
    0.2.0 (Cycle 2.1): attach bearer_config + revoked_token_store to
        app.state; share one IdentityTokenVerifier across both flows.
    0.1.0:             original cookie-only OAuth wiring.
"""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
import uvicorn

from .app import AppServices
from .bearer_store import BearerConfig, RevokedTokenStore
from .config import Settings, load_settings
from .oauth import OAuthCodeStore, OAuthFlowStore, OAuthStateStore, build_oauth_ui_app
from .oauth_dcr import OAuthClientStore
from .tools.admin import register_admin_tools
from .tools.attendance import register_attendance_tools
from .tools.crm import register_crm_tools
from .tools.expense import register_expense_tools
from .tools.hr import register_hr_tools
from .tools.projects import register_project_tools
from .tools.recruit import register_recruit_tools
from .tools.sale import register_sale_tools
from .tools.timesheet import register_timesheet_tools


def build_server() -> FastMCP:
    settings = load_settings()
    services = AppServices.build(settings)
    mcp = FastMCP(
        "Odoo CRM and Projects",
        stateless_http=True,
        json_response=True,
        host=settings.host,
        port=settings.port,
        # Mount streamable-http at root (`/`) instead of FastMCP's
        # default `/mcp` so marketplace remote-MCP clients can connect
        # using the bare base URL. SSE path retains its default `/sse`.
        streamable_http_path="/",
        token_verifier=services.identity,
        auth=AuthSettings(
            issuer_url=settings.identity_issuer or settings.public_url,
            resource_server_url=settings.public_url,
            required_scopes=[],
        ),
    )
    # Register all tool groups; each is independent and registers its own @mcp.tool() handlers
    register_admin_tools(mcp, services)
    register_crm_tools(mcp, services)
    register_project_tools(mcp, services)
    register_recruit_tools(mcp, services)
    register_hr_tools(mcp, services)
    register_attendance_tools(mcp, services)
    register_expense_tools(mcp, services)
    register_timesheet_tools(mcp, services)
    register_sale_tools(mcp, services)
    return mcp


def main() -> None:
    settings = load_settings()
    mcp = build_server()
    # For HTTP transports we always go through uvicorn so the full
    # OAuth-UI + bearer Starlette app is mounted. TLS is optional —
    # when cert files are empty the sidecar (nginx) terminates TLS
    # in front of plain uvicorn.
    if settings.transport in {"sse", "streamable-http"}:
        run_uvicorn_sse(mcp, settings)
        return
    mcp.run()


def run_uvicorn_sse(mcp: FastMCP, settings: Settings) -> None:
    google_client_id = settings.google_oauth_client_id
    # Streamable-http mounts at root (just `/`), SSE mounts at `/sse`.
    # Resource URL is what gets advertised as the OAuth resource
    # indicator — must match the path Claude/marketplace clients hit.
    if settings.transport == "streamable-http":
        mcp_asgi_app = mcp.streamable_http_app()
        resource_url = settings.public_url
    else:
        mcp_asgi_app = mcp.sse_app()
        resource_url = f"{settings.public_url}/sse"
    # Build the verifier once so the same instance backs both the cookie
    # flow and the headless bearer flow — keeps signature verification
    # consistent across all entry points.
    identity_verifier = AppServices.build(settings).identity
    app = build_oauth_ui_app(
        mcp_app=mcp_asgi_app,
        verifier=identity_verifier,
        odoo_url=settings.odoo_url,
        odoo_db_name=settings.odoo_db_name,
        public_url=settings.public_url,
        resource_url=resource_url,
        google_client_id=google_client_id,
        session_secret=settings.odoo_connector_secret,
    )
    app.state.oauth_state_store = OAuthStateStore()
    app.state.oauth_flow_store = OAuthFlowStore()
    app.state.oauth_code_store = OAuthCodeStore()
    # DCR client store: persists for process lifetime (in-memory).
    # Populated by POST /register; consumed by /authorize + /token.
    app.state.oauth_client_store = OAuthClientStore()
    app.state.google_client_id = google_client_id
    app.state.odoo_url = settings.odoo_url
    app.state.odoo_db_name = settings.odoo_db_name
    app.state.identity_issuer = settings.identity_issuer or settings.public_url
    app.state.resource_url = resource_url
    # Headless bearer-token flow state. Same secret as the cookie flow so
    # tokens issued via /auth/issue-token validate via the same verifier.
    app.state.bearer_config = BearerConfig(
        public_url=settings.public_url,
        session_secret=settings.odoo_connector_secret,
        odoo_url=settings.odoo_url,
        odoo_db_name=settings.odoo_db_name,
        verifier=identity_verifier,
    )
    app.state.revoked_token_store = RevokedTokenStore()
    # TLS is only enabled when BOTH cert + key are configured. Empty
    # values (the sidecar-frontend path) start uvicorn on plain HTTP.
    uvicorn_kwargs = {"host": settings.host, "port": settings.port}
    if settings.tls_cert_file and settings.tls_key_file:
        uvicorn_kwargs["ssl_certfile"] = str(settings.tls_cert_file)
        uvicorn_kwargs["ssl_keyfile"] = str(settings.tls_key_file)
    uvicorn.run(app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
