# ============================================================
# File: timesheet_actions.py
# Summary: Odoo controller actions for hr_timesheet entries.
#          Backed by account.analytic.line records that link to
#          project / task / employee.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced to the MCP layer for timesheet entries.
TIMESHEET_FIELDS = [
    "id",
    "name",
    "date",
    "unit_amount",
    "project_id",
    "task_id",
    "employee_id",
    "user_id",
]


def _employee_for_user(user):
    """Resolve the hr.employee tied to the active Odoo user (raise if none)."""
    employee = request.env["hr.employee"].with_user(user).search(
        [("user_id", "=", user.id)], limit=1
    )
    if not employee:
        raise ValueError("No employee record linked to this Odoo user")
    return employee


def list_entries(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List timesheet entries, optionally filtered by employee/project/dates."""
    # Filter to timesheet entries only (project_id set rules out generic analytic lines)
    domain: list[Any] = [("project_id", "!=", False)]
    if params.get("employee_id"):
        domain.append(("employee_id", "=", int(params["employee_id"])))
    if params.get("project_id"):
        domain.append(("project_id", "=", int(params["project_id"])))
    if params.get("date_from"):
        domain.append(("date", ">=", params["date_from"]))
    if params.get("date_to"):
        domain.append(("date", "<=", params["date_to"]))
    records = request.env["account.analytic.line"].with_user(user).search_read(
        domain,
        TIMESHEET_FIELDS,
        limit=int(params.get("limit", 30)),
        order="date desc",
    )
    return compact_records(records)


def create_entry(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a timesheet entry (hours of work on a project / task)."""
    values = dict(params["values"])
    # Default employee_id to caller if not supplied
    if not values.get("employee_id"):
        values["employee_id"] = _employee_for_user(user).id
    entry = request.env["account.analytic.line"].with_user(user).create(values)
    return {"id": entry.id, "message": "Timesheet entry created"}


def weekly_summary(user, params: dict[str, Any]) -> dict[str, Any]:
    """Return this-week timesheet totals for the caller's employee."""
    employee = _employee_for_user(user)
    # Compute Monday of current ISO week
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    records = request.env["account.analytic.line"].with_user(user).search_read(
        [
            ("employee_id", "=", employee.id),
            ("project_id", "!=", False),
            ("date", ">=", monday.isoformat()),
            ("date", "<=", sunday.isoformat()),
        ],
        TIMESHEET_FIELDS,
        order="date asc",
    )
    total = sum(r.get("unit_amount") or 0.0 for r in records)
    return {
        "employee_id": employee.id,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "entries": compact_records(records),
        "total_hours": round(total, 2),
    }
