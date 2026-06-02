from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


PROJECT_FIELDS = ["id", "name", "user_id", "partner_id", "company_id"]
TASK_FIELDS = [
    "id",
    "name",
    "project_id",
    "stage_id",
    "user_ids",
    "partner_id",
    "date_deadline",
    "priority",
    "state",
    "activity_state",
]


def list_projects(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List projects visible to the mapped Odoo user."""
    domain = [("name", "ilike", params["query"])] if params.get("query") else []
    records = request.env["project.project"].with_user(user).search_read(
        domain,
        PROJECT_FIELDS,
        limit=int(params.get("limit", 20)),
        order="write_date desc",
    )
    return compact_records(records)


def list_tasks(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List project tasks visible to the mapped Odoo user."""
    domain: list[Any] = []
    if params.get("project_id"):
        domain.append(("project_id", "=", int(params["project_id"])))
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))
    records = request.env["project.task"].with_user(user).search_read(
        domain,
        TASK_FIELDS,
        limit=int(params.get("limit", 30)),
        order="write_date desc",
    )
    return compact_records(records)


def list_task_stages(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List project task stages visible to the mapped Odoo user."""
    domain: list[Any] = []
    if params.get("project_id"):
        domain = ["|", ("project_ids", "=", False), ("project_ids", "in", [int(params["project_id"])])]
    records = request.env["project.task.type"].with_user(user).search_read(
        domain,
        ["id", "name", "sequence", "fold", "project_ids"],
        limit=int(params.get("limit", 50)),
        order="sequence asc",
    )
    return compact_records(records)


def create_task(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a project task as the mapped Odoo user."""
    task = request.env["project.task"].with_user(user).create(dict(params["values"]))
    return {"id": task.id, "message": "Project task created"}


def move_task_stage(user, params: dict[str, Any]) -> dict[str, Any]:
    """Move a visible project task to another stage."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    task.write({"stage_id": int(params["stage_id"])})
    return {"id": task.id, "message": "Project task stage updated"}


def add_comment(user, params: dict[str, Any]) -> dict[str, Any]:
    """Add a chatter comment to a visible project task."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    task.message_post(body=params["comment"], message_type="comment", subtype_xmlid="mail.mt_comment")
    return {"id": task.id, "message": "Project task comment added"}


def update_task(user, params: dict[str, Any]) -> dict[str, Any]:
    """Update fields on a visible project task including assignees and deadline."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    values = dict(params.get("values") or {})
    if not values:
        raise ValueError("No fields to update")
    task.write(values)
    return {"id": task.id, "message": "Project task updated"}
