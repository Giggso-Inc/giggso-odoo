# ============================================================
# File: hr_actions.py
# Summary: Odoo controller actions for hr employees and departments.
#          Read-only helpers callable via the signed MCP connector.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced to the MCP layer for employee records.
EMPLOYEE_FIELDS = [
    "id",
    "name",
    "work_email",
    "work_phone",
    "mobile_phone",
    "job_title",
    "job_id",
    "department_id",
    "parent_id",
    "company_id",
    "active",
]

# Fields surfaced to the MCP layer for department records.
DEPARTMENT_FIELDS = [
    "id",
    "name",
    "complete_name",
    "manager_id",
    "parent_id",
    "company_id",
    "total_employee",
]


def list_employees(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List employees visible to the mapped Odoo user."""
    # Optional ilike filter on employee name
    domain: list[Any] = []
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))
    if params.get("department_id"):
        domain.append(("department_id", "=", int(params["department_id"])))
    records = request.env["hr.employee"].with_user(user).search_read(
        domain,
        EMPLOYEE_FIELDS,
        limit=int(params.get("limit", 30)),
        order="name asc",
    )
    return compact_records(records)


def get_employee(user, params: dict[str, Any]) -> dict[str, Any]:
    """Return a single employee by id."""
    employee = (
        request.env["hr.employee"]
        .with_user(user)
        .browse(int(params["employee_id"]))
        .exists()
    )
    if not employee:
        raise ValueError("Employee not found or not visible")
    record = employee.read(EMPLOYEE_FIELDS)
    return compact_records(record)[0]


def list_departments(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List departments visible to the mapped Odoo user."""
    domain = [("name", "ilike", params["query"])] if params.get("query") else []
    records = request.env["hr.department"].with_user(user).search_read(
        domain,
        DEPARTMENT_FIELDS,
        limit=int(params.get("limit", 30)),
        order="name asc",
    )
    return compact_records(records)
