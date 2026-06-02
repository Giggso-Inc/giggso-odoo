from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from odoo import http
from odoo.http import request

from . import (
    activity_actions,
    admin_actions,
    attendance_actions,
    crm_actions,
    expense_actions,
    hr_actions,
    project_actions,
    recruit_actions,
    sale_actions,
    timesheet_actions,
)


# Module x action -> handler. Each tuple is reachable from the MCP server
# only when the addon is installed and the underlying Odoo module exists.
HANDLERS = {
    ("admin", "health"): admin_actions.health,
    ("admin", "capabilities"): admin_actions.capabilities,
    # crm
    ("crm", "search_opportunities"): crm_actions.search_opportunities,
    ("crm", "list_stale_opportunities"): crm_actions.list_stale_opportunities,
    ("crm", "list_stages"): crm_actions.list_stages,
    ("crm", "create_lead"): crm_actions.create_lead,
    ("crm", "add_note"): crm_actions.add_note,
    ("crm", "update_stage"): crm_actions.update_stage,
    ("crm", "update_opportunity"): crm_actions.update_opportunity,
    ("crm", "schedule_activity"): activity_actions.schedule_activity,
    # project
    ("project", "list_projects"): project_actions.list_projects,
    ("project", "list_tasks"): project_actions.list_tasks,
    ("project", "list_task_stages"): project_actions.list_task_stages,
    ("project", "create_task"): project_actions.create_task,
    ("project", "move_task_stage"): project_actions.move_task_stage,
    ("project", "add_comment"): project_actions.add_comment,
    ("project", "update_task"): project_actions.update_task,
    # recruit
    ("recruit", "list_jobs"): recruit_actions.list_jobs,
    ("recruit", "list_applicants"): recruit_actions.list_applicants,
    ("recruit", "list_applicant_stages"): recruit_actions.list_applicant_stages,
    ("recruit", "create_applicant"): recruit_actions.create_applicant,
    ("recruit", "move_applicant_stage"): recruit_actions.move_applicant_stage,
    ("recruit", "add_applicant_note"): recruit_actions.add_applicant_note,
    ("recruit", "update_applicant"): recruit_actions.update_applicant,
    # hr
    ("hr", "list_employees"): hr_actions.list_employees,
    ("hr", "get_employee"): hr_actions.get_employee,
    ("hr", "list_departments"): hr_actions.list_departments,
    # attendance
    ("attendance", "check_in"): attendance_actions.check_in,
    ("attendance", "check_out"): attendance_actions.check_out,
    ("attendance", "list_attendance"): attendance_actions.list_attendance,
    ("attendance", "today_summary"): attendance_actions.today_summary,
    # expense
    ("expense", "list_expenses"): expense_actions.list_expenses,
    ("expense", "create_expense"): expense_actions.create_expense,
    ("expense", "list_sheets"): expense_actions.list_sheets,
    ("expense", "submit_sheet"): expense_actions.submit_sheet,
    # timesheet
    ("timesheet", "list_entries"): timesheet_actions.list_entries,
    ("timesheet", "create_entry"): timesheet_actions.create_entry,
    ("timesheet", "weekly_summary"): timesheet_actions.weekly_summary,
    # sale
    ("sale", "list_orders"): sale_actions.list_orders,
    ("sale", "get_order"): sale_actions.get_order,
    ("sale", "create_quotation"): sale_actions.create_quotation,
    ("sale", "confirm_order"): sale_actions.confirm_order,
    ("sale", "add_order_line"): sale_actions.add_order_line,
    ("sale", "list_products"): sale_actions.list_products,
}


class OdooMcpController(http.Controller):
    """Signed HTTP entrypoint for MCP calls into Odoo."""

    @http.route("/odoo_mcp/action", type="http", auth="public", methods=["POST"], csrf=False)
    def action(self) -> http.Response:
        """Verify, dispatch, and return one MCP connector action."""
        raw_body = request.httprequest.get_data()
        try:
            self._verify_signature(raw_body)
            result = self._dispatch(json.loads(raw_body.decode("utf-8")))
            return self._json_response({"result": result})
        except Exception as exc:
            self._audit(actor_email="unknown", module="unknown", action="error", success=False, detail=str(exc))
            return self._json_response({"error": str(exc)}, status=400)

    def _dispatch(self, payload: dict[str, Any]) -> Any:
        """Map a signed request to a connector action."""
        actor_email = str(payload.get("actor_email") or "")
        module = str(payload.get("module") or "")
        action = str(payload.get("action") or "")
        params = payload.get("params") or {}
        if not actor_email: raise ValueError("actor_email is required")
        if not isinstance(params, dict): raise ValueError("params must be an object")

        handler = HANDLERS.get((module, action))
        if not handler:
            raise ValueError(f"Unsupported MCP action: {module}.{action}")
        result = handler(self._user_for_actor(actor_email), params)
        self._audit(actor_email=actor_email, module=module, action=action, success=True)
        return result

    def _verify_signature(self, body: bytes) -> None:
        """Verify the connector HMAC signature and timestamp."""
        secret = request.env["ir.config_parameter"].sudo().get_param("odoo_mcp_connector.signing_secret")
        if not secret:
            raise ValueError("Odoo MCP connector signing secret is not configured")
        timestamp = request.httprequest.headers.get("X-Odoo-MCP-Timestamp", "")
        signature = request.httprequest.headers.get("X-Odoo-MCP-Signature", "")
        if not timestamp or not signature:
            raise ValueError("Missing Odoo MCP signature headers")
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise ValueError("Odoo MCP request timestamp is outside the allowed window")
        message = timestamp.encode("utf-8") + b"." + body
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Odoo MCP request signature")

    def _user_for_actor(self, actor_email: str):
        """Resolve an SSO actor email to an active Odoo user."""
        user = request.env["res.users"].sudo().search(
            [("active", "=", True), "|", ("login", "=", actor_email), ("email", "=", actor_email)],
            limit=1,
        )
        if not user:
            raise ValueError(f"No active Odoo user found for MCP actor: {actor_email}")
        return user

    def _audit(self, *, actor_email: str, module: str, action: str, success: bool, detail: str = "") -> None:
        """Write a connector audit event."""
        request.env["odoo.mcp.audit"].sudo().create({
            "actor_email": actor_email, "module": module, "action": action,
            "success": success, "detail": detail,
        })

    def _json_response(self, payload: dict[str, Any], status: int = 200) -> http.Response:
        """Return a JSON HTTP response."""
        return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")], status=status)
