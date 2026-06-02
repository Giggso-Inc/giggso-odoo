# ============================================================
# File: recruit_actions.py
# Summary: Odoo controller actions for hr.recruitment (jobs, applicants).
#          Read + write helpers callable via the signed MCP connector.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced to the MCP layer for applicant records.
APPLICANT_FIELDS = [
    "id",
    "name",
    "partner_name",
    "email_from",
    "partner_phone",
    "job_id",
    "stage_id",
    "user_id",
    "kanban_state",
    "create_date",
    "date_closed",
    "active",
]

# Fields surfaced for hr.job postings.
JOB_FIELDS = [
    "id",
    "name",
    "department_id",
    "user_id",
    "state",
    "no_of_recruitment",
    "no_of_hired_employee",
]


def list_jobs(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List recruitment job postings visible to the mapped Odoo user."""
    # ilike filter on job title when a query is supplied
    domain = [("name", "ilike", params["query"])] if params.get("query") else []
    records = request.env["hr.job"].with_user(user).search_read(
        domain,
        JOB_FIELDS,
        limit=int(params.get("limit", 20)),
        order="write_date desc",
    )
    return compact_records(records)


def list_applicants(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List recruitment applicants, optionally filtered by job_id or query."""
    # Build domain incrementally so only supplied filters apply
    domain: list[Any] = []
    if params.get("job_id"):
        domain.append(("job_id", "=", int(params["job_id"])))
    if params.get("query"):
        domain.append(("partner_name", "ilike", params["query"]))
    records = request.env["hr.applicant"].with_user(user).search_read(
        domain,
        APPLICANT_FIELDS,
        limit=int(params.get("limit", 30)),
        order="create_date desc",
    )
    return compact_records(records)


def list_applicant_stages(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List recruitment kanban stages."""
    records = request.env["hr.recruitment.stage"].with_user(user).search_read(
        [],
        ["id", "name", "sequence", "fold", "hired_stage"],
        limit=int(params.get("limit", 50)),
        order="sequence asc",
    )
    return compact_records(records)


def create_applicant(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create an applicant as the mapped Odoo user."""
    # values dict is validated upstream in the MCP tool wrapper
    applicant = request.env["hr.applicant"].with_user(user).create(dict(params["values"]))
    return {"id": applicant.id, "message": "Applicant created"}


def move_applicant_stage(user, params: dict[str, Any]) -> dict[str, Any]:
    """Move an applicant to another kanban stage."""
    applicant = (
        request.env["hr.applicant"]
        .with_user(user)
        .browse(int(params["applicant_id"]))
        .exists()
    )
    if not applicant:
        raise ValueError("Applicant not found or not visible")
    applicant.write({"stage_id": int(params["stage_id"])})
    return {"id": applicant.id, "message": "Applicant stage updated"}


def update_applicant(user, params: dict[str, Any]) -> dict[str, Any]:
    """Update fields on a visible recruitment applicant."""
    applicant = (
        request.env["hr.applicant"]
        .with_user(user)
        .browse(int(params["applicant_id"]))
        .exists()
    )
    if not applicant:
        raise ValueError("Applicant not found or not visible")
    values = dict(params.get("values") or {})
    if not values:
        raise ValueError("No fields to update")
    applicant.write(values)
    return {"id": applicant.id, "message": "Applicant updated"}


def add_applicant_note(user, params: dict[str, Any]) -> dict[str, Any]:
    """Add an internal chatter note to an applicant."""
    applicant = (
        request.env["hr.applicant"]
        .with_user(user)
        .browse(int(params["applicant_id"]))
        .exists()
    )
    if not applicant:
        raise ValueError("Applicant not found or not visible")
    applicant.message_post(
        body=params["note"],
        message_type="comment",
        subtype_xmlid="mail.mt_note",
    )
    return {"id": applicant.id, "message": "Applicant note added"}
