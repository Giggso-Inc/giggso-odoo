# ============================================================
# File: timesheet.py
# Summary: MCP tool registrations for the timesheet domain.
#          Wraps account.analytic.line (hr_timesheet) actions as
#          timesheet_* tools exposed to MCP clients.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_timesheet_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def timesheet_list(
        employee_id: int | None = None,
        project_id: int | None = None,
        date_from: str = "",
        date_to: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List timesheet entries visible to the authenticated user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="timesheet",
            action="list_entries",
            params={
                "employee_id": employee_id,
                "project_id": project_id,
                "date_from": date_from,
                "date_to": date_to,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def timesheet_create_entry(
        project_id: int,
        unit_amount: float,
        name: str = "",
        task_id: int | None = None,
        date: str = "",
        employee_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a timesheet entry (hours worked on a project / task)."""
        actor_email = authenticated_login()
        # Build the values dict only with provided fields
        values: dict[str, Any] = {
            "project_id": project_id,
            "unit_amount": unit_amount,
            "name": name or "/",
        }
        if task_id:
            values["task_id"] = task_id
        if date:
            values["date"] = date
        if employee_id:
            values["employee_id"] = employee_id
        result = services.call_odoo(
            actor_email=actor_email,
            module="timesheet",
            action="create_entry",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="account.analytic.line",
            record_id=int(dict(result)["id"]),
            payload={"project_id": project_id, "unit_amount": unit_amount},
        )
        return dict(result)

    @mcp.tool()
    def timesheet_weekly_summary() -> dict[str, Any]:
        """Return this-week timesheet totals for the caller's employee."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="timesheet",
            action="weekly_summary",
            params={},
        )
        return dict(result)
