# ============================================================
# File: recruit.py
# Summary: MCP tool registrations for the recruitment domain.
#          Wraps hr.job and hr.applicant connector actions as
#          recruit_* tools exposed to MCP clients.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_recruit_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def recruit_list_jobs(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """List recruitment job postings visible to the authenticated Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="list_jobs",
            params={"query": query, "limit": min(limit, 50)},
        )
        return list(result)

    @mcp.tool()
    def recruit_list_applicants(
        job_id: int | None = None,
        query: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List applicants, optionally filtered by job_id and partner name."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="list_applicants",
            params={"job_id": job_id, "query": query, "limit": min(limit, 75)},
        )
        return list(result)

    @mcp.tool()
    def recruit_list_applicant_stages(limit: int = 50) -> list[dict[str, Any]]:
        """List recruitment kanban stages."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="list_applicant_stages",
            params={"limit": min(limit, 100)},
        )
        return list(result)

    @mcp.tool()
    def recruit_create_applicant(
        partner_name: str,
        job_id: int,
        email: str = "",
        phone: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a recruitment applicant."""
        actor_email = authenticated_login()
        # Build the values dict only with provided optional fields
        values: dict[str, Any] = {
            "partner_name": partner_name,
            "name": partner_name,
            "job_id": job_id,
        }
        if email:
            values["email_from"] = email
        if phone:
            values["partner_phone"] = phone
        if description:
            values["description"] = description
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="create_applicant",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="hr.applicant",
            record_id=int(dict(result)["id"]),
            payload={"job_id": job_id, "fields": sorted(values.keys())},
        )
        return dict(result)

    @mcp.tool()
    def recruit_move_applicant_stage(
        applicant_id: int,
        stage_id: int,
    ) -> dict[str, Any]:
        """Move an applicant to another recruitment kanban stage."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="move_applicant_stage",
            params={"applicant_id": applicant_id, "stage_id": stage_id},
        )
        services.audit.write(
            actor=actor_email,
            action="write.stage",
            model="hr.applicant",
            record_id=applicant_id,
            payload={"stage_id": stage_id},
        )
        return dict(result)

    @mcp.tool()
    def recruit_add_applicant_note(
        applicant_id: int,
        note: str,
    ) -> dict[str, Any]:
        """Add an internal chatter note to an applicant."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="recruit",
            action="add_applicant_note",
            params={"applicant_id": applicant_id, "note": note},
        )
        services.audit.write(
            actor=actor_email,
            action="message_post",
            model="hr.applicant",
            record_id=applicant_id,
            payload={"body_length": len(note)},
        )
        return dict(result)
