"""Shared delete operations for MCP tools (CRM, Sales, Projects)."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_delete_tools(mcp: FastMCP, services: AppServices) -> None:
    """Register delete tools for CRM leads, order lines, and project tasks."""

    @mcp.tool()
    def crm_delete_lead(lead_id: int) -> dict[str, Any]:
        """Delete a CRM lead/opportunity. WARNING: This action is permanent."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="delete_lead",
            params={"lead_id": lead_id},
        )
        services.audit.write(
            actor=actor_email, action="unlink", model="crm.lead",
            record_id=lead_id, payload={"name": result.get("name"), "deleted": True},
        )
        return dict(result)

    @mcp.tool()
    def sale_delete_order_line(order_id: int, line_id: int) -> dict[str, Any]:
        """Delete a line from a sale order. Recalculates totals. Draft/sent orders only."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="sale", action="delete_order_line",
            params={"order_id": order_id, "line_id": line_id},
        )
        services.audit.write(
            actor=actor_email, action="unlink", model="sale.order.line",
            record_id=line_id, payload={"order_id": order_id, "deleted": True},
        )
        return dict(result)

    @mcp.tool()
    def project_delete_task(task_id: int) -> dict[str, Any]:
        """Delete a project task. WARNING: This action is permanent."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="project", action="delete_task",
            params={"task_id": task_id},
        )
        services.audit.write(
            actor=actor_email, action="unlink", model="project.task",
            record_id=task_id, payload={"name": result.get("name"), "deleted": True},
        )
        return dict(result)
