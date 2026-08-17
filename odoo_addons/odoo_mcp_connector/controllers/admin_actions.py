from __future__ import annotations

from odoo.http import request


def health(user, _params: dict) -> dict:
    """Return connector and mapped-user health information."""
    return {
        "status": "ok",
        "odoo_user_id": user.id,
        "odoo_user_login": user.login,
        "database": request.env.cr.dbname,
    }


def capabilities(user, _params: dict) -> dict:
    """Return MCP tools allowed by the mapped user's Odoo permissions."""
    tools = {}
    if request.env["crm.lead"].with_user(user).check_access_rights("read", raise_exception=False):
        tools["crm"] = [
            "crm_search_opportunities",
            "crm_list_stale_opportunities",
            "crm_list_stages",
            "crm_create_lead",
            "crm_add_note",
            "crm_update_stage",
        ]
    if request.env["project.task"].with_user(user).check_access_rights("read", raise_exception=False):
        tools["project"] = [
            "project_list_projects",
            "project_list_tasks",
            "project_list_task_stages",
            "project_get_task",
            "project_create_task",
            "project_update_task",
            "project_move_task_stage",
            "project_add_comment",
            "project_attach_file",
            "project_read_attachment",
            "project_add_followers",
            "project_remove_followers",
        ]
    return {
        "odoo_user_login": user.login,
        "allowed_modules": sorted(tools),
        "tools": tools,
    }
