from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_partner_activity_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def partner_schedule_activity(
        partner_id: int,
        activity_type: str = "To-Do",
        summary: str = "",
        deadline: str = "",
        note: str = "",
        user_login: str = "",
    ) -> dict[str, Any]:
        """Schedule a follow-up activity on an Odoo contact (res.partner).

        activity_type: 'To-Do', 'Email', 'Phone Call', 'Meeting'.
        deadline: YYYY-MM-DD, defaults to today.
        Returns {"activity_id": int}.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="schedule_activity",
            params={
                "partner_id": partner_id, "activity_type": activity_type,
                "summary": summary, "deadline": deadline, "note": note,
                "user_login": user_login,
            },
        )
        services.audit.write(
            actor=actor_email, action="activity_schedule", model="res.partner",
            record_id=partner_id, payload={"activity_type": activity_type},
        )
        return dict(result)

    @mcp.tool()
    def partner_post_message(
        partner_id: int,
        body: str,
        message_type: str = "comment",
    ) -> dict[str, Any]:
        """Post a chatter message on an Odoo contact.

        Use for HITL: "Suggested enrichment — approve?" on a contact card.
        message_type: 'comment' (visible to followers) or 'notification' (internal).
        Returns {"message_id": int}.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="post_message",
            params={"partner_id": partner_id, "body": body, "message_type": message_type},
        )
        services.audit.write(
            actor=actor_email, action="message_post", model="res.partner",
            record_id=partner_id, payload={"body_length": len(body)},
        )
        return dict(result)
