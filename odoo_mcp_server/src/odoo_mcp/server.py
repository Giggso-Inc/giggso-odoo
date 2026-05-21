from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
import uvicorn

from .app import AppServices
from .config import Settings, load_settings
from .oauth import OAuthStateStore, build_oauth_ui_app
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
    google_client_id = settings.google_oauth_client_id or settings.identity_audience
    app = build_oauth_ui_app(
        mcp_app=mcp.sse_app(),
        verifier=AppServices.build(settings).identity,
        public_url=settings.public_url,
        google_client_id=google_client_id,
        session_secret=settings.odoo_connector_secret,
    )
    app.state.oauth_state_store = OAuthStateStore()
    app.state.google_client_id = google_client_id
    app.state.identity_issuer = settings.identity_issuer or settings.public_url
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        ssl_certfile=str(settings.tls_cert_file),
        ssl_keyfile=str(settings.tls_key_file),
    )


if __name__ == "__main__":
    main()
