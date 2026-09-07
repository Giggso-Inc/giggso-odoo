"""Odoo MCP server entry point (v0.4.1).

Builds FastMCP, registers all tool modules, then runs uvicorn (HTTP
transports) or stdio. TLS is optional — nginx sidecar can terminate it.
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
from .tools.activity import register_activity_tools
from .tools.admin import register_admin_tools
from .tools.attendance import register_attendance_tools
from .tools.crm import register_crm_tools
from .tools.delete import register_delete_tools
from .tools.expense import register_expense_tools
from .tools.hr import register_hr_tools
from .tools.partners import register_partner_tools
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
        streamable_http_path="/",  # root URL; marketplace clients use bare base URL
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
    register_recruit_tools(mcp, services)
    register_hr_tools(mcp, services)
    register_attendance_tools(mcp, services)
    register_expense_tools(mcp, services)
    register_timesheet_tools(mcp, services)
    register_sale_tools(mcp, services)
    register_activity_tools(mcp, services)
    register_delete_tools(mcp, services)
    register_partner_tools(mcp, services)
    return mcp


def main() -> None:
    settings = load_settings()
    mcp = build_server()
    if settings.transport in {"sse", "streamable-http"}:
        run_uvicorn_sse(mcp, settings)
        return
    mcp.run()


def run_uvicorn_sse(mcp: FastMCP, settings: Settings) -> None:
    google_client_id = settings.google_oauth_client_id
    if settings.transport == "streamable-http":
        mcp_asgi_app = mcp.streamable_http_app()
        resource_url = settings.public_url
    else:
        mcp_asgi_app = mcp.sse_app()
        resource_url = f"{settings.public_url}/sse"
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
    app.state.oauth_client_store = OAuthClientStore()
    app.state.google_client_id = google_client_id
    app.state.odoo_url = settings.odoo_url
    app.state.odoo_db_name = settings.odoo_db_name
    app.state.identity_issuer = settings.identity_issuer or settings.public_url
    app.state.resource_url = resource_url
    app.state.bearer_config = BearerConfig(
        public_url=settings.public_url,
        session_secret=settings.odoo_connector_secret,
        odoo_url=settings.odoo_url,
        odoo_db_name=settings.odoo_db_name,
        verifier=identity_verifier,
    )
    app.state.revoked_token_store = RevokedTokenStore()
    uvicorn_kwargs = {
        "host": settings.host,
        "port": settings.port,
        # Keep idle streamable-http / SSE connections alive long enough
        # for Claude Desktop and mcp-remote to reuse them between tool
        # calls. Default of 5 s causes premature disconnects that the
        # client sees as timeouts. 120 s matches nginx proxy_read_timeout.
        "timeout_keep_alive": 3600,  # 60 min — prevents token churn from idle reconnects
    }
    if settings.tls_cert_file and settings.tls_key_file:
        uvicorn_kwargs["ssl_certfile"] = str(settings.tls_cert_file)
        uvicorn_kwargs["ssl_keyfile"] = str(settings.tls_key_file)
    uvicorn.run(app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
