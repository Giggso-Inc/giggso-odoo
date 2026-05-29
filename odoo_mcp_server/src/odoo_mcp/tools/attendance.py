# ============================================================
# File: attendance.py
# Summary: MCP tool registrations for the attendance domain.
#          Wraps hr.attendance check-in/out + list helpers as
#          attendance_* tools exposed to MCP clients.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_attendance_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def attendance_check_in() -> dict[str, Any]:
        """Check in the authenticated user's employee right now (UTC)."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="attendance",
            action="check_in",
            params={},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="hr.attendance",
            record_id=int(dict(result)["id"]),
            payload={"event": "check_in"},
        )
        return dict(result)

    @mcp.tool()
    def attendance_check_out() -> dict[str, Any]:
        """Check out the authenticated user's current open attendance."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="attendance",
            action="check_out",
            params={},
        )
        services.audit.write(
            actor=actor_email,
            action="write",
            model="hr.attendance",
            record_id=int(dict(result)["id"]),
            payload={"event": "check_out"},
        )
        return dict(result)

    @mcp.tool()
    def attendance_list(
        employee_id: int | None = None,
        date_from: str = "",
        date_to: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List attendance records (defaults to all visible to the user)."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="attendance",
            action="list_attendance",
            params={
                "employee_id": employee_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def attendance_today_summary() -> dict[str, Any]:
        """Return today's attendance entries + worked hours for the caller."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="attendance",
            action="today_summary",
            params={},
        )
        return dict(result)
