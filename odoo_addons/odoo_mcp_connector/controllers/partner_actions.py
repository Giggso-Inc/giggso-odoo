from __future__ import annotations

from typing import Any

from odoo.http import request

from .partner_utils import format_partner, resolve_country, resolve_parent_company, resolve_state

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
    return {"found": True, "partner": format_partner(record)}


def create_partner(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a new res.partner with the full BRD field set."""
    name = str(params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    vals: dict[str, Any] = {"name": name, "is_company": bool(params.get("is_company", False))}
    for param_key, odoo_field in _SCALAR_FIELD_MAP.items():
        if param_key != "name" and params.get(param_key):
            vals[odoo_field] = str(params[param_key]).strip()

    country_id = None
    if params.get("country_name"):
        country_id = resolve_country(user, params["country_name"])
        if country_id:
            vals["country_id"] = country_id
    if params.get("state_name"):
        sid = resolve_state(user, params["state_name"], country_id=country_id)
        if sid:
            vals["state_id"] = sid
    if params.get("parent_company_name"):
        vals["parent_id"] = resolve_parent_company(user, params["parent_company_name"])

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

    country_id = record.country_id.id if record.country_id else None
    if params.get("country_name"):
        if not record.country_id:
            cid = resolve_country(user, params["country_name"])
            if cid:
                updates["country_id"] = cid
                country_id = cid
        else:
            skipped.append("country_id")

    if params.get("state_name"):
        if not record.state_id:
            sid = resolve_state(user, params["state_name"], country_id=country_id)
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
