# ============================================================
# File: expense.py
# Summary: MCP tool registrations for the expense domain.
#          Wraps hr.expense and hr.expense.sheet actions as
#          expense_* tools exposed to MCP clients.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_expense_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def expense_list(
        employee_id: int | None = None,
        state: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List expense lines visible to the authenticated Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="expense",
            action="list_expenses",
            params={
                "employee_id": employee_id,
                "state": state,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def expense_create(
        name: str,
        total_amount: float,
        product_id: int | None = None,
        employee_id: int | None = None,
        date: str = "",
        reference: str = "",
    ) -> dict[str, Any]:
        """Create a new expense line (defaults employee to the caller)."""
        actor_email = authenticated_login()
        # Build values dict with only the fields the user supplied
        values: dict[str, Any] = {"name": name, "total_amount": total_amount}
        if product_id:
            values["product_id"] = product_id
        if employee_id:
            values["employee_id"] = employee_id
        if date:
            values["date"] = date
        if reference:
            values["reference"] = reference
        result = services.call_odoo(
            actor_email=actor_email,
            module="expense",
            action="create_expense",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="hr.expense",
            record_id=int(dict(result)["id"]),
            payload={"fields": sorted(values.keys())},
        )
        return dict(result)

    @mcp.tool()
    def expense_list_sheets(
        employee_id: int | None = None,
        state: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List expense sheets (reports) visible to the user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="expense",
            action="list_sheets",
            params={
                "employee_id": employee_id,
                "state": state,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def expense_submit_sheet(sheet_id: int) -> dict[str, Any]:
        """Submit an expense sheet (draft -> submitted)."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="expense",
            action="submit_sheet",
            params={"sheet_id": sheet_id},
        )
        services.audit.write(
            actor=actor_email,
            action="action_submit_sheet",
            model="hr.expense.sheet",
            record_id=sheet_id,
            payload={"event": "submit"},
        )
        return dict(result)
