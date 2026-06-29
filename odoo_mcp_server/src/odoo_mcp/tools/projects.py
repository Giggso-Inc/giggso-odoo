from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login



def register_project_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def project_list_projects(
        query: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List projects visible to the given Odoo user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="project", action="list_projects",
            params={"query": query, "limit": min(limit, 50)},
        )
        return list(result)

    @mcp.tool()
    def project_get_task(
        task_id: int,
    ) -> dict[str, Any]:
        """Get full details of a project task: title, description, stage, assignees, tags,
        deadline, priority, state, chatter comments, and attachments (with file content)."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="get_task",
            params={"task_id": task_id},
        )
        return dict(result)

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
            actor_email=actor_email, module="project", action="list_task_stages",
            params={"project_id": project_id, "limit": min(limit, 100)},
        )
        return list(result)

    @mcp.tool()
    def project_create_task(
        project_id: int,
        name: str,
        description: str = "",
        deadline: str = "",
        assignee_email: str = "",
        tag_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a project task as the given Odoo user.

        assignee_email: optional — Odoo login or email of the user to assign
        the task to.  When omitted the task is assigned to the caller.
        Passed as a top-level connector param (not inside values{}) so the
        Odoo addon can resolve it to a res.users record and build the correct
        Many2many write command before calling create().

        tag_names: optional list of tag name strings (e.g. ["Bug", "Sprint 3"]).
        Tags are matched by name (case-insensitive); new tags are created automatically
        if no match is found.
        """
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
            params={"values": values, "assignee_email": assignee_email, "tag_names": tag_names or []},
        )
        services.audit.write(
            actor=actor_email,
            action="create",
            model="project.task",
            record_id=int(dict(result)["id"]),
            payload={
                "project_id": project_id,
                "fields": sorted(values.keys()),
                "assignee_email": assignee_email or actor_email,
            },
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
            actor=actor_email, action="write.stage", model="project.task",
            record_id=task_id, payload={"stage_id": stage_id},
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
            actor=actor_email, action="message_post", model="project.task",
            record_id=task_id, payload={"body_length": len(comment)},
        )
        return dict(result)

    @mcp.tool()
    def project_update_task(
        task_id: int,
        name: str = "",
        description: str = "",
        deadline: str = "",
        priority: str = "",
        assignee_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Update a task: name, description, deadline, priority (0=normal/1=high), assignee_ids."""
        actor_email = authenticated_login()
        values: dict[str, Any] = {}
        if name: values["name"] = name
        if description: values["description"] = description
        if deadline: values["date_deadline"] = deadline
        if priority in {"0", "1"}: values["priority"] = priority
        if assignee_ids is not None: values["user_ids"] = [(6, 0, assignee_ids)]
        if not values:
            raise ValueError("No fields to update — provide name, description, deadline, priority, or assignee_ids")
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="update_task",
            params={"task_id": task_id, "values": values},
        )
        services.audit.write(
            actor=actor_email, action="write", model="project.task",
            record_id=task_id, payload={"fields": sorted(values.keys())},
        )
        return dict(result)


