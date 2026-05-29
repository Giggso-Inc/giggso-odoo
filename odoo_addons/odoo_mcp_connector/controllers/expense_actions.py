# ============================================================
# File: expense_actions.py
# Summary: Odoo controller actions for hr.expense.
#          Create / list / submit helpers callable via the
#          signed MCP connector.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced to the MCP layer for individual expense lines.
EXPENSE_FIELDS = [
    "id",
    "name",
    "employee_id",
    "product_id",
    "total_amount",
    "currency_id",
    "date",
    "state",
    "sheet_id",
    "payment_mode",
    "reference",
]

# Fields surfaced for hr.expense.sheet records.
SHEET_FIELDS = [
    "id",
    "name",
    "employee_id",
    "state",
    "total_amount",
    "currency_id",
    "expense_line_ids",
    "accounting_date",
]


def _employee_for_user(user):
    """Resolve the hr.employee tied to the active Odoo user (raise if none)."""
    employee = request.env["hr.employee"].with_user(user).search(
        [("user_id", "=", user.id)], limit=1
    )
    if not employee:
        raise ValueError("No employee record linked to this Odoo user")
    return employee


def list_expenses(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List expense lines visible to the mapped Odoo user."""
    domain: list[Any] = []
    if params.get("employee_id"):
        domain.append(("employee_id", "=", int(params["employee_id"])))
    if params.get("state"):
        domain.append(("state", "=", params["state"]))
    records = request.env["hr.expense"].with_user(user).search_read(
        domain,
        EXPENSE_FIELDS,
        limit=int(params.get("limit", 30)),
        order="date desc",
    )
    return compact_records(records)


def create_expense(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create an hr.expense for the caller (or specified employee)."""
    values = dict(params["values"])
    # Default employee_id to caller's own employee record
    if not values.get("employee_id"):
        values["employee_id"] = _employee_for_user(user).id
    expense = request.env["hr.expense"].with_user(user).create(values)
    return {"id": expense.id, "message": "Expense created"}


def list_sheets(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List expense sheets (reports) visible to the mapped user."""
    domain: list[Any] = []
    if params.get("employee_id"):
        domain.append(("employee_id", "=", int(params["employee_id"])))
    if params.get("state"):
        domain.append(("state", "=", params["state"]))
    records = request.env["hr.expense.sheet"].with_user(user).search_read(
        domain,
        SHEET_FIELDS,
        limit=int(params.get("limit", 30)),
        order="create_date desc",
    )
    return compact_records(records)


def submit_sheet(user, params: dict[str, Any]) -> dict[str, Any]:
    """Move an expense sheet from draft to submitted via action_submit_sheet."""
    sheet = (
        request.env["hr.expense.sheet"]
        .with_user(user)
        .browse(int(params["sheet_id"]))
        .exists()
    )
    if not sheet:
        raise ValueError("Expense sheet not found or not visible")
    sheet.action_submit_sheet()
    return {"id": sheet.id, "state": sheet.state, "message": "Expense sheet submitted"}
