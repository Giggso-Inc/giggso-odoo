from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_partner_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def partner_find_by_email(
        email: str,
    ) -> dict[str, Any]:
        """Look up an Odoo contact by email address.

        Use this BEFORE partner_create to avoid duplicates.
        Returns {"found": true, "partner": {...}} or {"found": false, "partner": null}.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="find_by_email",
            params={"email": email},
        )
        return dict(result)

    @mcp.tool()
    def partner_create(
        name: str,
        email: str = "",
        phone: str = "",
        mobile: str = "",
        function: str = "",
        street: str = "",
        city: str = "",
        state_name: str = "",
        zip_code: str = "",
        country_name: str = "",
        website: str = "",
        is_company: bool = False,
        parent_company_name: str = "",
    ) -> dict[str, Any]:
        """Create a new Odoo contact with the full BRD field set.

        function: job title. state_name/country_name: resolved by name to Odoo IDs.
        parent_company_name: finds or creates the linked company partner.
        Returns {"id": int, "name": str}.
        """
        actor_email = authenticated_login()
        params = {
            "name": name, "email": email, "phone": phone, "mobile": mobile,
            "function": function, "street": street, "city": city,
            "state_name": state_name, "zip_code": zip_code,
            "country_name": country_name, "website": website,
            "is_company": is_company, "parent_company_name": parent_company_name,
        }
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="create", params=params,
        )
        services.audit.write(
            actor=actor_email, action="create", model="res.partner",
            record_id=int(dict(result)["id"]), payload={"name": name},
        )
        return dict(result)

    @mcp.tool()
    def partner_enrich(
        partner_id: int,
        name: str = "",
        email: str = "",
        phone: str = "",
        mobile: str = "",
        function: str = "",
        street: str = "",
        city: str = "",
        state_name: str = "",
        zip_code: str = "",
        country_name: str = "",
        website: str = "",
    ) -> dict[str, Any]:
        """Enrich an existing Odoo contact — writes ONLY to fields currently blank.

        Never overwrites a field that already has a value (BRD enrich-only rule).
        Returns {"partner_id": int, "updated_fields": [...], "skipped_fields": [...]}.
        """
        actor_email = authenticated_login()
        params = {
            "partner_id": partner_id, "name": name, "email": email, "phone": phone,
            "mobile": mobile, "function": function, "street": street, "city": city,
            "state_name": state_name, "zip_code": zip_code,
            "country_name": country_name, "website": website,
        }
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="enrich", params=params,
        )
        services.audit.write(
            actor=actor_email, action="write", model="res.partner",
            record_id=partner_id, payload={"fields": dict(result).get("updated_fields", [])},
        )
        return dict(result)

    @mcp.tool()
    def partner_find_or_enrich(
        email: str,
        name: str = "",
        phone: str = "",
        mobile: str = "",
        function: str = "",
        street: str = "",
        city: str = "",
        state_name: str = "",
        zip_code: str = "",
        country_name: str = "",
        website: str = "",
        parent_company_name: str = "",
    ) -> dict[str, Any]:
        """Core contact-sync operation: find a contact by email, enrich if found, create if not.

        Returns {"action": "updated"|"created", "partner_id": int, "detail": {...}}.
        """
        actor_email = authenticated_login()
        params = {
            "email": email, "name": name, "phone": phone, "mobile": mobile,
            "function": function, "street": street, "city": city,
            "state_name": state_name, "zip_code": zip_code,
            "country_name": country_name, "website": website,
            "parent_company_name": parent_company_name,
        }
        result = services.call_odoo(
            actor_email=actor_email, module="partner", action="find_or_enrich", params=params,
        )
        services.audit.write(
            actor=actor_email, action="find_or_enrich", model="res.partner",
            record_id=int(dict(result)["partner_id"]), payload={"action": dict(result).get("action")},
        )
        return dict(result)

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
