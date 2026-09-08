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
        include_attachment_content: bool = False,
    ) -> dict[str, Any]:
        """Get full details of a project task: title, description, stage, assignees, tags,
        deadline, priority, state, chatter comments, attachment metadata, subtasks, and followers.

        Returns:
        - create_uid: {id, name, email} — who created the task
        - create_uid_restricted: True if caller lacks email read access (email omitted)
        - parent_id: {id, name} or null — parent task if this is a subtask
        - child_ids: [{id, name, stage_id, state}] — subtasks of this task
        - followers: [{id, name, email}] — current task followers
        - comments: [{id, author_id, body, date}] — public chatter messages
        - attachments: [{id, name, mimetype, file_size}] — attached files

        include_attachment_content: set True to include base64 file content (files under 5 MB only).
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="get_task",
            params={"task_id": task_id, "include_attachment_content": include_attachment_content},
        )
        return dict(result)

    @mcp.tool()
    def project_list_tasks(
        project_id: int | None = None,
        query: str = "",
        stage_id: int | None = None,
        stage_name: str = "",
        assignee_email: str = "",
        created_by_email: str = "",
        created_after: str = "",
        created_before: str = "",
        state: str = "",
        limit: int = 30,
    ) -> dict[str, Any]:
        """List tasks visible to the given Odoo user.

        Returns {"tasks": [...], "count": N, "truncated": bool}.
        truncated=True means the limit was reached — more tasks may exist;
        narrow your filter or increase limit (max 75).

        All filters are optional and combinable:
        - project_id: restrict to one project
        - query: task name contains (case-insensitive)
        - stage_id: exact Kanban stage ID
        - stage_name: Kanban stage name partial match, e.g. "In Progress"
        - assignee_email: tasks assigned to this user (login or email)
        - created_by_email: tasks created/raised by this user (login or email)
        - created_after: ISO 8601 date, e.g. "2026-07-27"
        - created_before: ISO 8601 date
        - state: personal task state — in_progress | changes_requested | approved | cancelled | done

        Each task includes create_uid {id, name} — the reporter.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="list_tasks",
            params={
                "project_id": project_id,
                "query": query,
                "stage_id": stage_id,
                "stage_name": stage_name,
                "assignee_email": assignee_email,
                "created_by_email": created_by_email,
                "created_after": created_after,
                "created_before": created_before,
                "state": state,
                "limit": min(limit, 75),
            },
        )
        return dict(result)

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
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a project task as the given Odoo user.

        assignee_email: Odoo login or email of the assignee. Defaults to the caller.
        tag_names: list of tag strings — matched case-insensitively; created if missing
          (requires project manager group).
        parent_id: optional ID of a parent task — creates this task as a subtask.
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
            params={
                "values": values,
                "assignee_email": assignee_email,
                "tag_names": tag_names or [],
                "parent_id": parent_id,
            },
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
                "parent_id": parent_id,
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
        mention_emails: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a chatter comment to a project task as the given Odoo user.

        mention_emails: optional list of user emails to notify/mention.
        Each email is resolved to a res.partner and passed to message_post,
        triggering Odoo's native chatter notification to those users.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="add_comment",
            params={"task_id": task_id, "comment": comment, "partner_emails": mention_emails or []},
        )
        services.audit.write(
            actor=actor_email, action="message_post", model="project.task",
            record_id=task_id, payload={"body_length": len(comment), "mentions": len(mention_emails or [])},
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
        parent_id: int | None = None,
        tag_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a task: name, description, deadline, priority (0=normal/1=high),
        assignee_ids, parent_id (subtask linkage), or tag_names (replaces existing tags).

        Set parent_id=0 to detach from a parent task.
        tag_names replaces the full tag list — pass all tags you want, not just new ones.
        """
        actor_email = authenticated_login()
        values: dict[str, Any] = {}
        if name: values["name"] = name
        if description: values["description"] = description
        if deadline: values["date_deadline"] = deadline
        if priority in {"0", "1"}: values["priority"] = priority
        if assignee_ids is not None: values["user_ids"] = [(6, 0, assignee_ids)]
        if not values and parent_id is None and tag_names is None:
            raise ValueError("No fields to update — provide at least one param")
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="update_task",
            params={
                "task_id": task_id,
                "values": values,
                "parent_id": parent_id,
                "tag_names": tag_names,
            },
        )
        services.audit.write(
            actor=actor_email, action="write", model="project.task",
            record_id=task_id, payload={"fields": sorted(values.keys())},
        )
        return dict(result)

    @mcp.tool()
    def project_attach_file(
        task_id: int,
        filename: str,
        content_base64: str,
        mimetype: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload a file attachment to a project task.

        content_base64: the file content encoded as a base64 string.
        Files are capped at 5 MB. Returns {id, name, message}.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="attach_file",
            params={
                "task_id": task_id,
                "filename": filename,
                "mimetype": mimetype,
                "content_base64": content_base64,
            },
        )
        services.audit.write(
            actor=actor_email, action="attach", model="project.task",
            record_id=task_id, payload={"filename": filename, "mimetype": mimetype},
        )
        return dict(result)

    @mcp.tool()
    def project_read_attachment(
        attachment_id: int,
    ) -> dict[str, Any]:
        """Read the content of a single task attachment by its ID.

        Attachment IDs are returned by project_get_task in the "attachments" list.

        Returns:
        - id, name, mimetype, file_size — metadata
        - text_content: decoded UTF-8 string for text files (markdown, JSON, CSV,
          plain text, XML, JS) — immediately readable, no decoding needed
        - content_base64: raw base64 for binary files (PDF, images, etc.)
        - decode_error: present only if a text file could not be decoded as UTF-8

        Files over 5 MB are rejected.

        Typical PR-review workflow:
          1. project_get_task(task_id=X) → find attachment named "tdd.md" → note its id
          2. project_read_attachment(attachment_id=Y) → get text_content
          3. Use text_content as context while reviewing the PR diff
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="get_attachment",
            params={"attachment_id": attachment_id},
        )
        return dict(result)

    @mcp.tool()
    def project_add_followers(
        task_id: int,
        partner_emails: list[str],
    ) -> dict[str, Any]:
        """Subscribe users as followers of a project task.

        Followers receive Odoo chatter notifications on all future updates
        to the task (comments, stage moves, field changes).

        partner_emails: list of email addresses or Odoo logins to subscribe.
        Only internal Odoo users are subscribed; portal/external partners are silently skipped.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="add_followers",
            params={"task_id": task_id, "partner_emails": partner_emails},
        )
        return dict(result)

    @mcp.tool()
    def project_remove_followers(
        task_id: int,
        partner_emails: list[str],
    ) -> dict[str, Any]:
        """Unsubscribe users from a project task's follower list.

        partner_emails: list of email addresses or Odoo logins to remove.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="project",
            action="remove_followers",
            params={"task_id": task_id, "partner_emails": partner_emails},
        )
        return dict(result)

    @mcp.tool()
    def project_set_task_state(
        task_id: int,
        state: str,
    ) -> dict[str, Any]:
        """Set the personal state (status pill) of a project task.

        state must be one of: in_progress | changes_requested | approved | cancelled | done
        (the connector translates this to Odoo's actual internal code, e.g.
        'done' -> '1_done', before writing — pass the friendly word here.)

        NOTE: this is NOT the Kanban board column. Use project_move_task_stage
        to change which column the task sits in; use this to change the
        personal status indicator on the task card.
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="project", action="set_task_state",
            params={"task_id": task_id, "state": state},
        )
        services.audit.write(
            actor=actor_email, action="write.state", model="project.task",
            record_id=task_id, payload={"state": state},
        )
        return dict(result)

    @mcp.tool()
    def project_get_tasks_bulk(
        task_ids: list[int],
    ) -> dict[str, Any]:
        """Fetch full detail for multiple project tasks in one call (max 100 IDs).

        Use after project_list_tasks returns a set of task IDs and you need
        full field data (description, assignee names, tags, deadline, state)
        for all of them without N sequential project_get_task calls.

        Returns {"tasks": [...], "count": int}. Does NOT include comments,
        attachments, or followers — call project_get_task individually for those.

        Pattern:
          1. project_list_tasks(project_id=X, limit=75) -> collect task ids
          2. project_get_tasks_bulk(task_ids=[...]) -> full fields for all
        """
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="project", action="get_tasks_bulk",
            params={"task_ids": task_ids},
        )
        return dict(result)
