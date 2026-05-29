# ============================================================
# File: hr.py
# Summary: MCP tool registrations for the HR domain.
#          Wraps hr.employee and hr.department read actions as
#          hr_* tools exposed to MCP clients.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_hr_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def hr_list_employees(
        query: str = "",
        department_id: int | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List employees visible to the authenticated Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="hr",
            action="list_employees",
            params={
                "query": query,
                "department_id": department_id,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def hr_get_employee(employee_id: int) -> dict[str, Any]:
        """Return a single employee record by id."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="hr",
            action="get_employee",
            params={"employee_id": employee_id},
        )
        return dict(result)

    @mcp.tool()
    def hr_list_departments(
        query: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List departments visible to the authenticated Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="hr",
            action="list_departments",
            params={"query": query, "limit": min(limit, 75)},
        )
        return list(result)
