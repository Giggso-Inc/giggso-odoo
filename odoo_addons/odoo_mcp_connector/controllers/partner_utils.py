from __future__ import annotations

from typing import Any

from odoo.http import request

# message_post accepts 'email' and 'user_notification', both of which have
# irreversible side effects (an actual SMTP send) that a chatter tool must
# not expose. Only comment/notification are chatter-safe.
ALLOWED_MESSAGE_TYPES = frozenset({"comment", "notification"})


def validate_message_type(message_type: str) -> str:
    """Reject any message_type that could trigger an outbound email send."""
    if message_type not in ALLOWED_MESSAGE_TYPES:
        raise ValueError(
            f"message_type must be one of: {', '.join(sorted(ALLOWED_MESSAGE_TYPES))}"
        )
    return message_type


def resolve_country(user, country_name: str) -> int | None:
    """Resolve a country name to its Odoo ID."""
    record = request.env["res.country"].with_user(user).search(
        [("name", "=ilike", country_name)], limit=1
    )
    return record.id if record else None


def resolve_state(user, state_name: str, country_id: int | None = None) -> int | None:
    """Resolve a state/province name to its Odoo ID, scoped by country when known.

    Many state names collide across countries (e.g. "Georgia", "Victoria",
    "Cordoba"). Without a country_id filter, limit=1 returns whichever row
    was inserted first — silently wrong for any country other than that one.
    Callers should resolve country first and thread its id in here.
    """
    domain: list[Any] = [("name", "=ilike", state_name)]
    if country_id:
        domain.append(("country_id", "=", country_id))
    record = request.env["res.country.state"].with_user(user).search(domain, limit=1)
    return record.id if record else None


def resolve_parent_company(user, company_name: str) -> int:
    """Find or create a company partner by exact name; return its ID.

    Uses an exact "=" match (not "=ilike") so case-variant names don't
    silently collide onto an unrelated existing company. This does not
    fully close the race window: two concurrent calls with the same exact
    name can still both miss the search and both create a company, since
    Odoo has no unique constraint on res.partner.name. Callers running
    high-concurrency import flows should de-duplicate company creation
    on their own side.
    """
    Partner = request.env["res.partner"].with_user(user)
    company = Partner.search([("name", "=", company_name), ("is_company", "=", True)], limit=1)
    if company:
        return company.id
    return Partner.create({"name": company_name, "is_company": True}).id


_OPTIONAL_SCALAR_FIELDS = (
    "email", "phone", "mobile", "function", "street", "city", "zip", "website",
)


def format_partner(record: Any) -> dict[str, Any]:
    """Serialise a res.partner record to a clean dict.

    Uses getattr() with a fallback for the optional contact fields rather
    than direct attribute access. Some Odoo deployments customise or strip
    fields off res.partner (e.g. a privacy/PII module, a lightweight
    partner variant) — direct attribute access on a field that isn't
    registered on the compiled model raises AttributeError and would take
    down every partner lookup. A field genuinely missing on this instance
    is reported as null rather than crashing the whole response.
    """
    def many2one(val):
        return {"id": val.id, "name": val.name} if val else None

    result: dict[str, Any] = {
        "id": record.id,
        "name": record.name,
        "is_company": record.is_company,
    }
    for field in _OPTIONAL_SCALAR_FIELDS:
        result[field] = getattr(record, field, False) or None
    result["state"] = many2one(getattr(record, "state_id", False))
    result["country"] = many2one(getattr(record, "country_id", False))
    result["company"] = many2one(getattr(record, "parent_id", False))
    return result
