from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


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


def register_project_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def project_list_projects(
        query: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List projects visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="list_projects",
            params={"query": query, "limit": min(limit, 50)},
        )
        return list(result)

    @mcp.tool()
    def project_list_tasks(
        project_id: int | None = None,
        query: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List tasks visible to the given Odoo user, optionally filtered by project."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="list_tasks",
            params={"project_id": project_id, "query": query, "limit": min(limit, 75)},
        )
        return list(result)

    @mcp.tool()
    def project_list_task_stages(
        project_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List Project task stages visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="list_task_stages",
            params={"project_id": project_id, "limit": min(limit, 100)},
        )
        return list(result)

    @mcp.tool()
    def project_create_task(
        project_id: int,
        name: str,
        description: str = "",
        deadline: str = "",
    ) -> dict[str, Any]:
        """Create a project task as the given Odoo user."""
        actor_email = authenticated_login()
        values: dict[str, Any] = {"project_id": project_id, "name": name}
        if description:
            values["description"] = description
        if deadline:
            values["date_deadline"] = deadline
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="create_task",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="project.task",
            record_id=int(dict(result)["id"]),
            payload={"project_id": project_id, "fields": sorted(values.keys())},
        )
        return dict(result)

    @mcp.tool()
    def project_move_task_stage(
        task_id: int,
        stage_id: int,
    ) -> dict[str, Any]:
        """Move a task to another Kanban stage as the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="move_task_stage",
            params={"task_id": task_id, "stage_id": stage_id},
        )
        services.audit.write(
            actor=actor_email,
            action="write.stage",
            model="project.task",
            record_id=task_id,
            payload={"stage_id": stage_id},
        )
        return dict(result)

    @mcp.tool()
    def project_add_comment(
        task_id: int,
        comment: str,
    ) -> dict[str, Any]:
        """Add a chatter comment to a project task as the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="add_comment",
            params={"task_id": task_id, "comment": comment},
        )
        services.audit.write(
            actor=actor_email,
            action="message_post",
            model="project.task",
            record_id=task_id,
            payload={"body_length": len(comment)},
        )
        return dict(result)
