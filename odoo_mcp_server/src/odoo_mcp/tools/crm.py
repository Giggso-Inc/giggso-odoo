from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login



def register_crm_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def crm_search_opportunities(
        query: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search CRM leads/opportunities visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="search_opportunities",
            params={"query": query, "limit": min(limit, 50)},
        )
        return list(result)

    @mcp.tool()
    def crm_list_stale_opportunities(
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List visible CRM opportunities that have no planned next activity."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="list_stale_opportunities",
            params={"limit": min(limit, 50)},
        )
        return list(result)

    @mcp.tool()
    def crm_list_stages(
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List CRM stages visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="list_stages",
            params={"limit": min(limit, 100)},
        )
        return list(result)

    @mcp.tool()
    def crm_create_lead(
        name: str,
        contact_name: str = "",
        email: str = "",
        phone: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a CRM lead as the given Odoo user."""
        actor_email = authenticated_login()
        values: dict[str, Any] = {
            "name": name,
            "type": "lead",
        }
        if contact_name:
            values["contact_name"] = contact_name
        if email:
            values["email_from"] = email
        if phone:
            values["phone"] = phone
        if description:
            values["description"] = description
        result = services.call_odoo(
            actor_email=actor_email,
            module="crm",
            action="create_lead",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email, action="create", model="crm.lead",
            record_id=int(dict(result)["id"]), payload={"fields": sorted(values.keys())},
        )
        return dict(result)

    @mcp.tool()
    def crm_add_note(
        lead_id: int,
        note: str,
    ) -> dict[str, Any]:
        """Add a chatter note to a CRM lead/opportunity as the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="add_note",
            params={"lead_id": lead_id, "note": note},
        )
        services.audit.write(
            actor=actor_email, action="message_post", model="crm.lead",
            record_id=lead_id, payload={"body_length": len(note)},
        )
        return dict(result)

    @mcp.tool()
    def crm_update_stage(
        lead_id: int,
        stage_id: int,
    ) -> dict[str, Any]:
        """Move a CRM lead/opportunity to a stage visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="update_stage",
            params={"lead_id": lead_id, "stage_id": stage_id},
        )
        services.audit.write(
            actor=actor_email, action="write.stage", model="crm.lead",
            record_id=lead_id, payload={"stage_id": stage_id},
        )
        return dict(result)

    @mcp.tool()
    def crm_update_opportunity(
        lead_id: int,
        name: str = "",
        expected_revenue: float | None = None,
        probability: float | None = None,
        deadline: str = "",
        salesperson_id: int | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Update a CRM opportunity: name, revenue, probability, deadline, salesperson, description."""
        actor_email = authenticated_login()
        values: dict[str, Any] = {}
        if name: values["name"] = name
        if description: values["description"] = description
        if deadline: values["date_deadline"] = deadline
        if expected_revenue is not None: values["expected_revenue"] = expected_revenue
        if probability is not None: values["probability"] = probability
        if salesperson_id is not None: values["user_id"] = salesperson_id
        if not values:
            raise ValueError("No fields to update — provide name, revenue, probability, deadline, salesperson_id, or description")
        result = services.call_odoo(
            actor_email=actor_email,
            module="crm",
            action="update_opportunity",
            params={"lead_id": lead_id, "values": values},
        )
        services.audit.write(
            actor=actor_email, action="write", model="crm.lead",
            record_id=lead_id, payload={"fields": sorted(values.keys())},
        )
        return dict(result)
