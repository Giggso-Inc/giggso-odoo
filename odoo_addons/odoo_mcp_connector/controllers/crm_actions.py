from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


# message_post accepts 'email' and 'user_notification', both of which trigger
# an irreversible SMTP send — a chatter tool must not expose those.
_ALLOWED_MESSAGE_TYPES = frozenset({"comment", "notification"})


CRM_FIELDS = [
    "id",
    "name",
    "partner_id",
    "contact_name",
    "email_from",
    "phone",
    "stage_id",
    "user_id",
    "team_id",
    "probability",
    "expected_revenue",
    "date_deadline",
    "activity_state",
]


def search_opportunities(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Search CRM leads and opportunities visible to the mapped user."""
    query = params.get("query")
    domain: list[Any] = []
    if query:
        # OR across title, customer email (exact, case-insensitive), and contact name (partial).
        # email_from uses =ilike (exact, no wildcards) to avoid partial-email false positives
        # while still matching regardless of the caller's casing.
        domain = [
            "|", "|",
            ("name", "ilike", query),
            ("email_from", "=ilike", query),
            ("contact_name", "ilike", query),
        ]
    records = request.env["crm.lead"].with_user(user).search_read(
        domain,
        CRM_FIELDS,
        limit=int(params.get("limit", 20)),
        order="write_date desc",
    )
    return compact_records(records)


def list_stale_opportunities(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List visible CRM opportunities without planned activities."""
    domain = [("type", "=", "opportunity"), ("activity_ids", "=", False)]
    records = request.env["crm.lead"].with_user(user).search_read(
        domain,
        CRM_FIELDS,
        limit=int(params.get("limit", 20)),
        order="write_date asc",
    )
    return compact_records(records)


def list_stages(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List CRM stages visible to the mapped user."""
    fields = ["id", "name", "sequence", "is_won", "fold"]
    records = request.env["crm.stage"].with_user(user).search_read(
        [],
        fields,
        limit=int(params.get("limit", 50)),
        order="sequence asc",
    )
    return compact_records(records)


def create_lead(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a CRM lead as the mapped Odoo user."""
    lead = request.env["crm.lead"].with_user(user).create(dict(params["values"]))
    return {"id": lead.id, "message": "CRM lead created"}


def add_note(user, params: dict[str, Any]) -> dict[str, Any]:
    """Add an internal note to a visible CRM lead."""
    lead = request.env["crm.lead"].with_user(user).browse(int(params["lead_id"])).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")
    lead.message_post(body=params["note"], message_type="comment", subtype_xmlid="mail.mt_note")
    return {"id": lead.id, "message": "CRM note added"}


def update_stage(user, params: dict[str, Any]) -> dict[str, Any]:
    """Move a visible CRM lead or opportunity to another stage."""
    lead = request.env["crm.lead"].with_user(user).browse(int(params["lead_id"])).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")
    lead.write({"stage_id": int(params["stage_id"])})
    return {"id": lead.id, "message": "CRM stage updated"}


def update_opportunity(user, params: dict[str, Any]) -> dict[str, Any]:
    """Update fields on a visible CRM lead or opportunity."""
    lead = request.env["crm.lead"].with_user(user).browse(int(params["lead_id"])).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")
    values = dict(params.get("values") or {})
    if not values:
        raise ValueError("No fields to update")
    lead.write(values)
    return {"id": lead.id, "message": "CRM opportunity updated"}


def crm_post_message(user, params: dict[str, Any]) -> dict[str, Any]:
    """Post a chatter message on a CRM lead, visible to followers.

    Distinct from add_note (mail.mt_note, internal-only): this uses
    mail.mt_comment so it notifies subscribed followers. Use for HITL
    "Suggested action — approve?" style notifications.
    """
    lead_id = int(params.get("lead_id") or 0)
    body = str(params.get("body") or "").strip()
    if not lead_id:
        raise ValueError("lead_id is required")
    if not body:
        raise ValueError("body is required")

    lead = request.env["crm.lead"].with_user(user).browse(lead_id).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")

    message_type = str(params.get("message_type") or "comment")
    if message_type not in _ALLOWED_MESSAGE_TYPES:
        raise ValueError(
            f"message_type must be one of: {', '.join(sorted(_ALLOWED_MESSAGE_TYPES))}"
        )
    msg_id = lead.message_post(
        body=body, message_type=message_type, subtype_xmlid="mail.mt_comment"
    ).id
    return {"message_id": msg_id}


def delete_lead(user, params: dict[str, Any]) -> dict[str, Any]:
    """Delete a CRM lead/opportunity. This action is permanent."""
    lead = request.env["crm.lead"].with_user(user).browse(int(params["lead_id"])).exists()
    if not lead:
        raise ValueError("CRM lead not found or not visible")
    lead_id = lead.id
    lead_name = lead.name
    lead.unlink()
    return {"id": lead_id, "name": lead_name, "message": "CRM lead deleted"}
