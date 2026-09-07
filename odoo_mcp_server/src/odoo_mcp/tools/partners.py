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
        result_dict = dict(result)
        new_id = result_dict.get("id")
        if isinstance(new_id, int):
            services.audit.write(
                actor=actor_email, action="create", model="res.partner",
                record_id=new_id, payload={"name": name},
            )
        return result_dict

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
        result_dict = dict(result)
        partner_id = result_dict.get("partner_id")
        if isinstance(partner_id, int):
            services.audit.write(
                actor=actor_email, action="find_or_enrich", model="res.partner",
                record_id=partner_id, payload={"action": result_dict.get("action")},
            )
        return result_dict
