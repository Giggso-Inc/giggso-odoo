from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_activity_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def crm_schedule_activity(
        lead_id: int,
        activity_type: str = "To-Do",
        summary: str = "",
        deadline: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        """Schedule a follow-up activity on a CRM lead.

        activity_type: To-Do, Email, Phone Call, or Meeting (default: To-Do).
        deadline: YYYY-MM-DD (defaults to today if omitted).
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="crm", action="schedule_activity",
            params={"lead_id": lead_id, "activity_type": activity_type,
                    "summary": summary, "deadline": deadline, "note": note},
        )
        services.audit.write(
            actor=actor_email, action="activity_schedule", model="crm.lead",
            record_id=lead_id, payload={"activity_type": activity_type},
        )
        return dict(result)

    @mcp.tool()
    def activity_list(
        res_model: str,
        res_id: int,
    ) -> dict[str, Any]:
        """List pending activities on any Odoo record.

        res_model: e.g. 'crm.lead', 'res.partner', 'project.task'
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="activity", action="list",
            params={"res_model": res_model, "res_id": res_id},
        )
        return dict(result)

    @mcp.tool()
    def activity_mark_done(
        activity_id: int,
        feedback: str = "",
    ) -> dict[str, Any]:
        """Mark a mail.activity as completed."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="activity", action="mark_done",
            params={"activity_id": activity_id, "feedback": feedback or "Done"},
        )
        services.audit.write(
            actor=actor_email, action="activity_done", model="mail.activity",
            record_id=activity_id, payload={},
        )
        return dict(result)
