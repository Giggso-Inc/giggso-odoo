from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_admin_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def odoo_health_check() -> dict[str, Any]:
        """Check whether the authenticated MCP user can authenticate to Odoo."""
        actor_email = authenticated_login()
        result = services.call_odoo(actor_email=actor_email, module="admin", action="health")
        return dict(result)

    @mcp.tool()
    def odoo_list_allowed_capabilities() -> dict[str, Any]:
        """List MCP modules enabled for the authenticated MCP user."""
        actor_email = authenticated_login()
        result = services.call_odoo(actor_email=actor_email, module="admin", action="capabilities")
        return dict(result)
