# ============================================================
# File: handlers.py
# Summary: MCP (module, action) -> handler routing table.
#          Split out of mcp_controller.py to keep both files
#          within the style guard line budget.
# ============================================================

from __future__ import annotations

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
    ("crm", "delete_lead"): crm_actions.delete_lead,
    ("crm", "schedule_activity"): activity_actions.schedule_activity,
    # project
    ("project", "list_projects"): project_actions.list_projects,
    ("project", "list_tasks"): project_actions.list_tasks,
    ("project", "list_task_stages"): project_actions.list_task_stages,
    ("project", "get_task"): project_actions.get_task,
    ("project", "create_task"): project_actions.create_task,
    ("project", "move_task_stage"): project_actions.move_task_stage,
    ("project", "add_comment"): project_actions.add_comment,
    ("project", "update_task"): project_actions.update_task,
    ("project", "delete_task"): project_actions.delete_task,
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
    ("sale", "delete_order_line"): sale_actions.delete_order_line,
}
