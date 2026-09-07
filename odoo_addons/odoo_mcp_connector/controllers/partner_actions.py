from __future__ import annotations

from datetime import date
from typing import Any

from odoo.http import request

PARTNER_FIELDS = [
    "id", "name", "email", "phone", "mobile", "function",
    "street", "city", "zip", "state_id", "country_id",
    "website", "parent_id", "is_company",
]

_SCALAR_FIELD_MAP = {
    "name": "name", "email": "email", "phone": "phone",
    "mobile": "mobile", "function": "function", "street": "street",
    "city": "city", "zip_code": "zip", "website": "website",
}


def _resolve_country(user, country_name: str) -> int | None:
    """Resolve a country name to its Odoo ID."""
    record = request.env["res.country"].with_user(user).search(
        [("name", "=ilike", country_name)], limit=1
    )
    return record.id if record else None


def _resolve_state(user, state_name: str) -> int | None:
    """Resolve a state/province name to its Odoo ID."""
    record = request.env["res.country.state"].with_user(user).search(
        [("name", "=ilike", state_name)], limit=1
    )
    return record.id if record else None


def _resolve_parent_company(user, company_name: str) -> int:
    """Find or create a company partner by name; return its ID."""
    Partner = request.env["res.partner"].with_user(user)
    company = Partner.search([("name", "=ilike", company_name), ("is_company", "=", True)], limit=1)
    if company:
        return company.id
    return Partner.create({"name": company_name, "is_company": True}).id


def _format_partner(record) -> dict[str, Any]:
    """Serialise a res.partner record to a clean dict."""
    def many2one(val):
        return {"id": val.id, "name": val.name} if val else None

    return {
        "id": record.id,
        "name": record.name,
        "email": record.email or None,
        "phone": record.phone or None,
        "mobile": record.mobile or None,
        "function": record.function or None,
        "street": record.street or None,
        "city": record.city or None,
        "zip": record.zip or None,
        "state": many2one(record.state_id),
        "country": many2one(record.country_id),
        "website": record.website or None,
        "company": many2one(record.parent_id),
        "is_company": record.is_company,
    }


def find_partner_by_email(user, params: dict[str, Any]) -> dict[str, Any]:
    """Look up a res.partner by email (case-insensitive exact match)."""
    email = str(params.get("email") or "").strip()
    if not email:
        raise ValueError("email is required")

    record = request.env["res.partner"].with_user(user).search(
        [("email", "=ilike", email)], limit=1
    )
    if not record:
        return {"found": False, "partner": None}
    return {"found": True, "partner": _format_partner(record)}


def create_partner(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a new res.partner with the full BRD field set."""
    name = str(params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    vals: dict[str, Any] = {"name": name, "is_company": bool(params.get("is_company", False))}
    for param_key, odoo_field in _SCALAR_FIELD_MAP.items():
        if param_key != "name" and params.get(param_key):
            vals[odoo_field] = str(params[param_key]).strip()
    if params.get("country_name"):
        cid = _resolve_country(user, params["country_name"])
        if cid:
            vals["country_id"] = cid
    if params.get("state_name"):
        sid = _resolve_state(user, params["state_name"])
        if sid:
            vals["state_id"] = sid
    if params.get("parent_company_name"):
        vals["parent_id"] = _resolve_parent_company(user, params["parent_company_name"])

    record = request.env["res.partner"].with_user(user).create(vals)
    return {"id": record.id, "name": record.name}


def enrich_partner(user, params: dict[str, Any]) -> dict[str, Any]:
    """Write to blank fields on an existing res.partner only — never overwrite verified data."""
    partner_id = int(params.get("partner_id") or 0)
    if not partner_id:
        raise ValueError("partner_id is required")

    record = request.env["res.partner"].with_user(user).browse(partner_id).exists()
    if not record:
        raise ValueError(f"Partner {partner_id} not found or access denied")

    updates: dict[str, Any] = {}
    skipped: list[str] = []

    for param_key, odoo_field in _SCALAR_FIELD_MAP.items():
        if params.get(param_key):
            if not getattr(record, odoo_field, False):
                updates[odoo_field] = str(params[param_key]).strip()
            else:
                skipped.append(odoo_field)

    if params.get("country_name"):
        if not record.country_id:
            cid = _resolve_country(user, params["country_name"])
            if cid:
                updates["country_id"] = cid
        else:
            skipped.append("country_id")

    if params.get("state_name"):
        if not record.state_id:
            sid = _resolve_state(user, params["state_name"])
            if sid:
                updates["state_id"] = sid
        else:
            skipped.append("state_id")

    if updates:
        record.write(updates)

    return {
        "partner_id": partner_id,
        "updated_fields": sorted(updates.keys()),
        "skipped_fields": sorted(skipped),
    }


def find_or_enrich_partner(user, params: dict[str, Any]) -> dict[str, Any]:
    """Search by email → enrich if found, create if not (BRD dedup rule)."""
    email = str(params.get("email") or "").strip()
    if not email:
        raise ValueError("email is required")

    existing = request.env["res.partner"].with_user(user).search(
        [("email", "=ilike", email)], limit=1
    )
    if existing:
        detail = enrich_partner(user, {**params, "partner_id": existing.id})
        return {"action": "updated", "partner_id": existing.id, "detail": detail}

    create_params = dict(params)
    if not create_params.get("name"):
        create_params["name"] = email
    detail = create_partner(user, create_params)
    return {"action": "created", "partner_id": detail["id"], "detail": detail}


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
        found = request.env["res.users"].sudo().search(
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

    message_type = str(params.get("message_type") or "comment")
    msg_id = record.message_post(
        body=body, message_type=message_type, subtype_xmlid="mail.mt_comment"
    ).id
    return {"message_id": msg_id}
