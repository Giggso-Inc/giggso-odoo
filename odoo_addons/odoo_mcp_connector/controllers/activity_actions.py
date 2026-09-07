from __future__ import annotations

import logging
from typing import Any

from odoo import fields
from odoo.http import request

_logger = logging.getLogger(__name__)


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


def list_activities(user, params: dict[str, Any]) -> dict[str, Any]:
    """List pending mail.activity records on any Odoo record."""
    res_model = str(params.get("res_model") or "").strip()
    res_id = int(params.get("res_id") or 0)
    if not res_model:
        raise ValueError("res_model is required")
    if not res_id:
        raise ValueError("res_id is required")

    activities = request.env["mail.activity"].with_user(user).search_read(
        [("res_model", "=", res_model), ("res_id", "=", res_id)],
        fields=["id", "activity_type_id", "summary", "date_deadline", "user_id", "note", "state"],
    )

    def _m2o(val):
        return {"id": val[0], "name": val[1]} if isinstance(val, (list, tuple)) and val else None

    return {
        "activities": [
            {
                "id": a["id"],
                "type": _m2o(a.get("activity_type_id")),
                "summary": a.get("summary") or None,
                "deadline": a.get("date_deadline"),
                "assigned_to": _m2o(a.get("user_id")),
                "note": a.get("note") or None,
                "state": a.get("state"),
            }
            for a in activities
        ]
    }


def mark_activity_done(user, params: dict[str, Any]) -> dict[str, Any]:
    """Mark a mail.activity as done."""
    activity_id = int(params.get("activity_id") or 0)
    if not activity_id:
        raise ValueError("activity_id is required")

    activity = request.env["mail.activity"].with_user(user).browse(activity_id).exists()
    if not activity:
        raise ValueError("Activity not found or not visible")

    feedback = str(params.get("feedback") or "Done via MCP")
    try:
        activity.action_feedback(feedback=feedback)
    except TypeError:
        # Older/newer Odoo signature mismatch — fall back to a direct unlink,
        # which removes the activity but does NOT post feedback as a chatter
        # note the way action_feedback would. Log so operators notice the
        # version drift and know feedback text was dropped for this call.
        _logger.warning(
            "mark_activity_done: action_feedback() signature mismatch on activity %s — "
            "falling back to unlink(); feedback text will not be recorded as a chatter note",
            activity_id,
        )
        activity.unlink()
    return {"success": True}
