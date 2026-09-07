from __future__ import annotations

from datetime import date
from typing import Any

from odoo.http import request

from .partner_utils import validate_message_type


def partner_schedule_activity(user, params: dict[str, Any]) -> dict[str, Any]:
    """Schedule a mail.activity on a res.partner (contact follow-up)."""
    partner_id = int(params.get("partner_id") or 0)
    if not partner_id:
        raise ValueError("partner_id is required")

    partner = request.env["res.partner"].with_user(user).browse(partner_id).exists()
    if not partner:
        raise ValueError(f"Partner {partner_id} not found or access denied")

    activity_type_name = str(params.get("activity_type") or "To-Do")
    atype = request.env["mail.activity.type"].with_user(user).search(
        [("name", "=ilike", activity_type_name)], limit=1
    )
    if not atype:
        raise ValueError(f"Activity type not found: {activity_type_name}")

    deadline = str(params.get("deadline") or date.today().isoformat())
    assign_user = user
    if params.get("user_login"):
        # Never sudo() this lookup — a caller without res.users read access
        # could otherwise probe whether an arbitrary login exists by
        # observing whether the activity assignee matches it. Only resolve
        # the login when the caller's own permissions allow reading users.
        Users = request.env["res.users"].with_user(user)
        if Users.check_access_rights("read", raise_exception=False):
            found = Users.search(
                [("login", "=", params["user_login"]), ("active", "=", True)], limit=1
            )
            if found:
                assign_user = found

    activity = request.env["mail.activity"].with_user(user).create({
        "activity_type_id": atype.id,
        "res_model": "res.partner",
        "res_id": partner_id,
        "summary": str(params.get("summary") or ""),
        "date_deadline": deadline,
        "note": str(params.get("note") or ""),
        "user_id": assign_user.id,
    })
    return {"activity_id": activity.id}


def partner_post_message(user, params: dict[str, Any]) -> dict[str, Any]:
    """Post a chatter message on a res.partner."""
    partner_id = int(params.get("partner_id") or 0)
    body = str(params.get("body") or "").strip()
    if not partner_id:
        raise ValueError("partner_id is required")
    if not body:
        raise ValueError("body is required")

    record = request.env["res.partner"].with_user(user).browse(partner_id).exists()
    if not record:
        raise ValueError(f"Partner {partner_id} not found or access denied")

    message_type = validate_message_type(str(params.get("message_type") or "comment"))
    msg_id = record.message_post(
        body=body, message_type=message_type, subtype_xmlid="mail.mt_comment"
    ).id
    return {"message_id": msg_id}
