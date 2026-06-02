from __future__ import annotations

from typing import Any

from odoo import fields
from odoo.http import request


def schedule_activity(user, params: dict[str, Any]) -> dict[str, Any]:
    """Schedule a mail.activity on a visible CRM lead."""
    lead = request.env["crm.lead"].with_user(user).browse(int(params["lead_id"])).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")
    activity_type = request.env["mail.activity.type"].sudo().search(
        [("name", "ilike", params.get("activity_type", "To-Do"))], limit=1
    )
    if not activity_type:
        raise ValueError(f"Activity type not found: {params.get('activity_type')}")
    deadline = params.get("deadline") or fields.Date.today()
    lead.activity_schedule(
        activity_type_id=activity_type.id,
        date_deadline=deadline,
        summary=params.get("summary", ""),
        note=params.get("note", ""),
    )
    return {"id": lead.id, "activity_type": activity_type.name, "message": "Activity scheduled"}
