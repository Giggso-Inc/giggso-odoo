# ============================================================
# File: attendance_actions.py
# Summary: Odoo controller actions for hr.attendance.
#          Check-in / check-out + list helpers callable via the
#          signed MCP connector.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced to the MCP layer for attendance records.
ATTENDANCE_FIELDS = [
    "id",
    "employee_id",
    "check_in",
    "check_out",
    "worked_hours",
]


def _employee_for_user(user):
    """Resolve the hr.employee tied to the active Odoo user (raise if none)."""
    employee = request.env["hr.employee"].with_user(user).search(
        [("user_id", "=", user.id)], limit=1
    )
    if not employee:
        raise ValueError("No employee record linked to this Odoo user")
    return employee


def list_attendance(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List attendance records, optionally scoped to an employee."""
    # Default scope is the caller's own employee unless caller passes employee_id
    domain: list[Any] = []
    if params.get("employee_id"):
        domain.append(("employee_id", "=", int(params["employee_id"])))
    if params.get("date_from"):
        domain.append(("check_in", ">=", params["date_from"]))
    if params.get("date_to"):
        domain.append(("check_in", "<=", params["date_to"]))
    records = request.env["hr.attendance"].with_user(user).search_read(
        domain,
        ATTENDANCE_FIELDS,
        limit=int(params.get("limit", 30)),
        order="check_in desc",
    )
    return compact_records(records)


def check_in(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create an open attendance (check_in now) for the caller."""
    employee = _employee_for_user(user)
    # Block double check-in: refuse if employee already has an open attendance
    existing = request.env["hr.attendance"].with_user(user).search(
        [("employee_id", "=", employee.id), ("check_out", "=", False)], limit=1
    )
    if existing:
        raise ValueError("Employee already has an open attendance")
    attendance = request.env["hr.attendance"].with_user(user).create({
        "employee_id": employee.id,
        "check_in": datetime.utcnow(),
    })
    return {"id": attendance.id, "message": "Checked in"}


def check_out(user, params: dict[str, Any]) -> dict[str, Any]:
    """Close the currently open attendance for the caller."""
    employee = _employee_for_user(user)
    attendance = request.env["hr.attendance"].with_user(user).search(
        [("employee_id", "=", employee.id), ("check_out", "=", False)], limit=1
    )
    if not attendance:
        raise ValueError("No open attendance to check out")
    attendance.write({"check_out": datetime.utcnow()})
    return {"id": attendance.id, "message": "Checked out"}


def today_summary(user, params: dict[str, Any]) -> dict[str, Any]:
    """Return today's attendance entries for the caller's employee."""
    employee = _employee_for_user(user)
    start = datetime.combine(datetime.utcnow().date(), time.min)
    records = request.env["hr.attendance"].with_user(user).search_read(
        [("employee_id", "=", employee.id), ("check_in", ">=", start)],
        ATTENDANCE_FIELDS,
        order="check_in asc",
    )
    total_hours = sum(r.get("worked_hours") or 0.0 for r in records)
    return {
        "employee_id": employee.id,
        "entries": compact_records(records),
        "total_worked_hours": round(total_hours, 2),
    }
