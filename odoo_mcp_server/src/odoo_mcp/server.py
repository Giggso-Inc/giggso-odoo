from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from .app import AppServices
from .config import load_settings
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
            issuer_url=settings.public_url,
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
    if settings.transport == "streamable-http":
        mcp.run(transport="streamable-http")
        return
    mcp.run()


if __name__ == "__main__":
    main()
