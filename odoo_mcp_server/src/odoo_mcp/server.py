"""
Odoo MCP server entry point.

Summary:
    Builds the FastMCP server, registers tool modules (admin, crm,
    projects), and either runs the stdio transport directly or hands
    off to run_https_sse() which mounts the OAuth + headless-bearer
    Starlette app via build_oauth_ui_app().

Version: 0.2.0
Execution context: process entry point (CLI `python -m odoo_mcp.server`)

Changelog:
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
from .tools.admin import register_admin_tools
from .tools.crm import register_crm_tools
from .tools.projects import register_project_tools


def build_server() -> FastMCP:
    settings = load_settings()
    services = AppServices.build(settings)
    mcp = FastMCP(
        "Odoo CRM and Projects",
        stateless_http=True,
        json_response=True,
        host=settings.host,
        port=settings.port,
        token_verifier=services.identity,
        auth=AuthSettings(
            issuer_url=settings.identity_issuer or settings.public_url,
            resource_server_url=settings.public_url,
            required_scopes=[],
        ),
    )
    register_admin_tools(mcp, services)
    register_crm_tools(mcp, services)
    register_project_tools(mcp, services)
    return mcp


def main() -> None:
    settings = load_settings()
    mcp = build_server()
    if settings.transport in {"sse", "streamable-http"}:
        if settings.tls_cert_file and settings.tls_key_file:
            run_https_sse(mcp, settings)
            return
        mcp.run(transport="sse")
        return
    mcp.run()


def run_https_sse(mcp: FastMCP, settings: Settings) -> None:
    google_client_id = settings.google_oauth_client_id
    resource_url = f"{settings.public_url}/sse"
    # Build the verifier once so the same instance backs both the cookie
    # flow and the headless bearer flow — keeps signature verification
    # consistent across all entry points.
    identity_verifier = AppServices.build(settings).identity
    app = build_oauth_ui_app(
        mcp_app=mcp.sse_app(),
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
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        ssl_certfile=str(settings.tls_cert_file),
        ssl_keyfile=str(settings.tls_key_file),
    )


if __name__ == "__main__":
    main()
