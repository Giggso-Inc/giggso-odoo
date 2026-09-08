from __future__ import annotations

import logging
import re
from typing import Any

from odoo.exceptions import AccessError
from odoo.http import request

from .utils import compact_records

_logger = logging.getLogger(__name__)

_STATE_PREFIX_RE = re.compile(r"^\d+_")
# Accept both spellings as client input — Odoo's actual internal code has
# been observed to use either 'canceled' or 'cancelled' depending on the
# instance (see set_task_state's docstring for why this can't be a static map).
_STATE_SPELLING_ALIASES = {"cancelled": "canceled"}


def _resolve_tag_ids(user, tag_names: list[str]) -> list[int]:
    """Resolve tag names to IDs, creating missing tags when the user is a project manager."""
    Tag = request.env["project.tags"].with_user(user)
    tag_ids = []
    for tag_name in tag_names:
        tag = Tag.search([("name", "=ilike", tag_name)], limit=1)
        if not tag:
            if not user.has_group("project.group_project_manager"):
                raise ValueError(
                    f"Tag '{tag_name}' does not exist and you do not have permission to create tags. "
                    "Ask a project manager to create it first."
                )
            tag = Tag.create({"name": tag_name})
        tag_ids.append(tag.id)
    return tag_ids


def _is_internal_user(partner) -> bool:
    """Return True when the partner has at least one active internal (non-portal) Odoo user."""
    return bool(partner.user_ids.filtered(lambda u: u.active and not u.share))


PROJECT_FIELDS = ["id", "name", "user_id", "partner_id", "company_id"]
TASK_DETAIL_FIELDS = [
    "id", "name", "description",
    "project_id", "stage_id", "user_ids",
    "create_uid", "parent_id", "child_ids",
    "partner_id", "company_id", "tag_ids",
    "date_deadline", "priority", "state", "activity_state",
    "create_date", "write_date",
]
TASK_FIELDS = [
    "id",
    "name",
    "description",
    "project_id",
    "stage_id",
    "user_ids",
    "create_uid",
    "parent_id",
    "partner_id",
    "date_deadline",
    "priority",
    "state",
    "activity_state",
    "create_date",
    "write_date",
]
_BULK_TASK_MAX = 100


def _normalize_state_key(code: str) -> str:
    """Strip Odoo's numeric Kanban-ordering prefix and lowercase.

    project.task.state codes look like '01_in_progress', '02_changes_requested',
    '1_done' — the numeric prefix controls Kanban sort order, not meaning.
    Stripping it gives a friendly key: 'in_progress', 'done'.
    """
    return _STATE_PREFIX_RE.sub("", code).lower()


def _state_code_map(user) -> dict[str, str]:
    """Build {friendly_name: actual_odoo_code} from the live selection field.

    Queried dynamically rather than hardcoded: the exact codes (and even
    the spelling of 'cancelled'/'canceled') vary by Odoo instance. A prior
    version of this connector hardcoded the friendly words themselves as
    the write value ('done'), which Odoo's selection field rejected outright
    since it only ever stores the prefixed code ('1_done') — no value
    satisfied both the connector's own input validator and Odoo's backend.
    Reading the live selection avoids re-introducing that mismatch.
    """
    selection = request.env["project.task"].with_user(user).fields_get(["state"])["state"]["selection"]
    return {_normalize_state_key(code): code for code, _label in selection}


def _resolve_state_code(user, friendly_state: str) -> str:
    """Translate a client-facing state name to Odoo's actual internal code."""
    key = _STATE_SPELLING_ALIASES.get(friendly_state.lower(), friendly_state.lower())
    code_map = _state_code_map(user)
    if key not in code_map:
        raise ValueError(
            f"Invalid state '{friendly_state}'. Must be one of: {', '.join(sorted(code_map))}"
        )
    return code_map[key]


def _enrich_user_ids(user, records: list[dict[str, Any]]) -> None:
    """Replace bare user_ids integer lists with [{id, name, email}] in place.

    Falls back to {id, name} when the caller lacks res.users.email read access.
    Uses a single batched read across all records — never per-record.
    """
    user_id_set: set[int] = set()
    for r in records:
        user_id_set.update(r.get("user_ids") or [])
    if not user_id_set:
        return
    try:
        rows = request.env["res.users"].with_user(user).browse(list(user_id_set)).read(
            ["id", "name", "email"]
        )
    except AccessError:
        rows = request.env["res.users"].with_user(user).browse(list(user_id_set)).read(
            ["id", "name"]
        )
    user_map = {row["id"]: row for row in rows}
    for r in records:
        r["user_ids"] = [user_map[uid] for uid in (r.get("user_ids") or []) if uid in user_map]


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


def list_tasks(user, params: dict[str, Any]) -> dict[str, Any]:
    """List project tasks visible to the mapped Odoo user.

    Returns {"tasks": [...], "count": N, "truncated": bool}.
    `truncated` is True when count equals the requested limit — more rows
    may exist; narrow the filter or increase limit.

    Supported filter params (all optional):
      project_id       — restrict to one project
      query            — task name contains (ilike)
      stage_id         — exact Kanban stage ID
      stage_name       — Kanban stage name partial match (used when stage_id absent)
      assignee_email   — tasks assigned to the user with this login or email
      created_by_email — tasks created/raised by the user with this login or email
      created_after    — ISO 8601 date string lower bound on create_date
      created_before   — ISO 8601 date string upper bound on create_date
      state            — personal task state: in_progress | changes_requested |
                         approved | cancelled | done
    """
    domain: list[Any] = []
    if params.get("project_id"):
        domain.append(("project_id", "=", int(params["project_id"])))
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))

    # Stage filter — prefer exact ID; fall back to name match.
    if params.get("stage_id"):
        domain.append(("stage_id", "=", int(params["stage_id"])))
    elif params.get("stage_name"):
        domain.append(("stage_id.name", "ilike", str(params["stage_name"])))

    # Assignee filter — Many2many traversal on login or email.
    if params.get("assignee_email"):
        email = str(params["assignee_email"]).strip()
        domain += ["|", ("user_ids.login", "=", email), ("user_ids.email", "=", email)]

    # Creator / reporter filter — Many2one path traversal on create_uid.
    if params.get("created_by_email"):
        email = str(params["created_by_email"]).strip()
        domain += ["|", ("create_uid.login", "=", email), ("create_uid.email", "=", email)]

    # Creation date window.
    if params.get("created_after"):
        domain.append(("create_date", ">=", str(params["created_after"])))
    if params.get("created_before"):
        domain.append(("create_date", "<=", str(params["created_before"])))

    # Personal task state (Odoo 17+ enum) — translate the friendly client
    # word to Odoo's actual internal code (e.g. 'done' -> '1_done'); a raw
    # equality on the friendly word never matches and silently returns zero
    # rows, since Odoo never stores the bare word as the field value.
    if params.get("state"):
        domain.append(("state", "=", _resolve_state_code(user, str(params["state"]))))

    lim = int(params.get("limit", 30))
    records = request.env["project.task"].with_user(user).search_read(
        domain,
        TASK_FIELDS,
        limit=lim,
        order="write_date desc",
    )
    _enrich_user_ids(user, records)
    items = compact_records(records)
    return {"tasks": items, "count": len(items), "truncated": len(items) >= lim}


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
    """Create a project task as the mapped Odoo user.

    user_ids is set explicitly before create() to bypass Odoo's default_get,
    which resolves self.env.user from the request context. On auth="public"
    routes request.env.user is the Public user (id=3); letting default_get
    fill user_ids would set the task owner to Public, which then fails the
    res.users read-access check and returns 400.
    """
    vals = dict(params["values"])
    assignee_email: str = str(params.get("assignee_email") or "").strip()
    if assignee_email:
        assignee = request.env["res.users"].sudo().search(
            [
                ("active", "=", True),
                "|",
                ("login", "=", assignee_email),
                ("email", "=", assignee_email),
            ],
            limit=1,
        )
        if not assignee:
            raise ValueError(f"No active Odoo user found for assignee: {assignee_email}")
        vals["user_ids"] = [(4, assignee.id)]
    elif "user_ids" not in vals:
        # Default to the authenticated actor — never let default_get pick Public.
        vals["user_ids"] = [(4, user.id)]

    # Optional subtask parent linkage — access-checked so callers cannot
    # enumerate tasks outside their visibility by trying arbitrary IDs.
    if params.get("parent_id"):
        parent = (
            request.env["project.task"]
            .with_user(user)
            .browse(int(params["parent_id"]))
            .exists()
        )
        if not parent:
            raise ValueError("Parent task not found or not visible")
        vals["parent_id"] = parent.id

    tag_names: list[str] = [n.strip() for n in (params.get("tag_names") or []) if n and n.strip()]
    if tag_names:
        vals["tag_ids"] = [(6, 0, _resolve_tag_ids(user, tag_names))]

    task = request.env["project.task"].with_user(user).create(vals)
    return {"id": task.id, "name": task.name, "message": "Project task created"}


def move_task_stage(user, params: dict[str, Any]) -> dict[str, Any]:
    """Move a visible project task to another stage."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    task.write({"stage_id": int(params["stage_id"])})
    return {"id": task.id, "message": "Project task stage updated"}


def add_comment(user, params: dict[str, Any]) -> dict[str, Any]:
    """Add a chatter comment to a visible project task.

    partner_emails: optional list of user emails to notify/mention.
    Resolves each to res.partner and passes as partner_ids to message_post,
    which triggers Odoo's native chatter notification to those users.
    """
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")

    partner_ids: list[int] = []
    for email in (params.get("partner_emails") or []):
        email = str(email).strip()
        if not email:
            continue
        partner = request.env["res.partner"].sudo().search(
            ["|", ("email", "=", email), ("user_ids.login", "=", email)], limit=1
        )
        # Only notify internal users — skip portal/external partners to prevent
        # leaking task content to accounts outside the organisation.
        if partner and _is_internal_user(partner):
            partner_ids.append(partner.id)

    task.message_post(
        body=params["comment"],
        message_type="comment",
        subtype_xmlid="mail.mt_comment",
        partner_ids=partner_ids or [],
    )
    return {"id": task.id, "message": "Project task comment added", "notified": len(partner_ids)}


def update_task(user, params: dict[str, Any]) -> dict[str, Any]:
    """Update fields on a visible project task including assignees, deadline, parent, and tags."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    values = dict(params.get("values") or {})

    if params.get("parent_id") is not None:
        if params["parent_id"]:
            parent = (
                request.env["project.task"]
                .with_user(user)
                .browse(int(params["parent_id"]))
                .exists()
            )
            if not parent:
                raise ValueError("Parent task not found or not visible")
            values["parent_id"] = parent.id
        else:
            values["parent_id"] = False

    tag_names: list[str] = [n.strip() for n in (params.get("tag_names") or []) if n and n.strip()]
    if tag_names:
        values["tag_ids"] = [(6, 0, _resolve_tag_ids(user, tag_names))]

    if not values:
        raise ValueError("No fields to update")
    task.write(values)
    return {"id": task.id, "message": "Project task updated"}


def delete_task(user, params: dict[str, Any]) -> dict[str, Any]:
    """Delete a project task. This action is permanent."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    task_id = task.id
    task_name = task.name
    task.unlink()
    return {"id": task_id, "name": task_name, "message": "Project task deleted"}


def get_task(user, params: dict[str, Any]) -> dict[str, Any]:
    """Return full details of a single project task including comments and attachments."""
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")

    rows = compact_records(task.read(TASK_DETAIL_FIELDS))
    if not rows:
        raise ValueError("Project task was deleted before it could be read")
    record = rows[0]

    # Enrich many2many assignees with name + email.
    if record.get("user_ids"):
        Users = request.env["res.users"].with_user(user).browse(record["user_ids"])
        try:
            assignees = Users.read(["id", "name", "email"])
            record["user_ids"] = [{"id": a["id"], "name": a["name"], "email": a.get("email") or ""} for a in assignees]
        except AccessError:
            assignees = Users.read(["id", "name"])
            record["user_ids"] = [{"id": a["id"], "name": a["name"]} for a in assignees]

    # Enrich create_uid (Many2one) to {id, name, email}.
    # If the caller lacks res.users.email access, downgrade to {id, name} and
    # surface create_uid_restricted=True so callers know the email was dropped.
    if task.create_uid:
        try:
            c = task.create_uid.with_user(user)
            record["create_uid"] = {"id": c.id, "name": c.name, "email": c.email or ""}
        except AccessError:
            record["create_uid"] = {"id": task.create_uid.id, "name": task.create_uid.name}
            record["create_uid_restricted"] = True

    # Enrich tags with names.
    if record.get("tag_ids"):
        tags = request.env["project.tags"].sudo().browse(record["tag_ids"]).read(["id", "name"])
        record["tag_ids"] = [{"id": t["id"], "name": t["name"]} for t in tags]

    # Enrich parent_id: compact_records leaves it as (id, name) pair — normalise.
    # record["parent_id"] is already compacted to {id, name} or None by compact_records.

    # Enrich child_ids (subtasks): replace raw ids with [{id, name, stage_id}].
    if record.get("child_ids"):
        child_rows = request.env["project.task"].with_user(user).browse(record["child_ids"]).read(
            ["id", "name", "stage_id", "state"]
        )
        record["child_ids"] = compact_records(child_rows)

    # Followers: mail.followers linked to this task — name + email of each partner.
    try:
        followers = request.env["mail.followers"].sudo().search_read(
            [("res_model", "=", "project.task"), ("res_id", "=", task.id)],
            ["partner_id"],
        )
        partner_ids_raw = [f["partner_id"][0] for f in followers if f.get("partner_id")]
        if partner_ids_raw:
            partners = request.env["res.partner"].sudo().browse(partner_ids_raw).read(["id", "name", "email"])
            record["followers"] = [{"id": p["id"], "name": p["name"], "email": p.get("email") or ""} for p in partners]
        else:
            record["followers"] = []
    except Exception:
        _logger.warning("get_task: failed to load followers for task %s", task.id, exc_info=True)
        record["followers"] = []

    # Chatter comments — public only (exclude internal notes).
    messages = request.env["mail.message"].with_user(user).search_read(
        [
            ("model", "=", "project.task"),
            ("res_id", "=", task.id),
            ("message_type", "in", ["comment", "email"]),
            ("subtype_id.internal", "=", False),
        ],
        ["id", "author_id", "body", "date", "message_type"],
        order="date desc",
        limit=50,
    )
    record["comments"] = compact_records(messages)

    # Attachments — metadata always; binary content only when explicitly requested.
    _MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
    include_content: bool = bool(params.get("include_attachment_content"))
    attachment_fields = ["id", "name", "mimetype", "file_size", "create_date"]
    attachment_domain = [("res_model", "=", "project.task"), ("res_id", "=", task.id)]
    if include_content:
        attachment_domain.append(("file_size", "<=", _MAX_ATTACHMENT_BYTES))
        attachment_fields.append("datas")
    attachments = request.env["ir.attachment"].with_user(user).search_read(
        attachment_domain,
        attachment_fields,
        order="create_date desc",
        limit=20,
    )
    record["attachments"] = compact_records(attachments)

    return record


_TEXT_MIMETYPES = {
    "text/plain", "text/markdown", "text/csv", "text/html",
    "application/json", "application/xml", "text/xml",
    "application/javascript", "text/javascript",
}


def get_attachment(user, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a single attachment by ID and return its content.

    Returns metadata plus one of:
      - text_content: decoded UTF-8 string (for text/* and common text formats)
      - content_base64: raw base64 string (for binary files)

    text_content is returned when mimetype is text/*, application/json,
    application/xml, or similar — so markdown, CSV, JSON, and plain text
    files are immediately readable without base64 decoding.

    Files over 5 MB are rejected.
    """
    _MAX_BYTES = 5 * 1024 * 1024
    attachment = request.env["ir.attachment"].with_user(user).browse(int(params["attachment_id"])).exists()
    if not attachment:
        raise ValueError("Attachment not found or not accessible")
    if attachment.file_size and attachment.file_size > _MAX_BYTES:
        raise ValueError(f"Attachment exceeds 5 MB limit ({attachment.file_size} bytes)")

    import base64
    raw_b64: str = attachment.datas or ""
    if not raw_b64:
        raise ValueError("Attachment has no content")

    mimetype: str = attachment.mimetype or "application/octet-stream"
    # Normalise: "text/markdown; charset=utf-8" → "text/markdown"
    base_mime = mimetype.split(";")[0].strip().lower()
    is_text = base_mime in _TEXT_MIMETYPES or base_mime.startswith("text/")

    result: dict[str, Any] = {
        "id": attachment.id,
        "name": attachment.name,
        "mimetype": mimetype,
        "file_size": attachment.file_size,
    }
    if is_text:
        try:
            result["text_content"] = base64.b64decode(raw_b64).decode("utf-8")
        except Exception:
            result["content_base64"] = raw_b64
            result["decode_error"] = "File reported as text but could not be decoded as UTF-8"
    else:
        result["content_base64"] = raw_b64

    return result


def attach_file(user, params: dict[str, Any]) -> dict[str, Any]:
    """Upload a file attachment to a project task.

    Requires params: task_id, filename, mimetype, content_base64.
    The content_base64 value must be a valid base64-encoded string.
    Files are capped at 5 MB; larger payloads are rejected before create().
    """
    _MAX_BYTES = 5 * 1024 * 1024
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")

    import base64
    content_b64: str = str(params.get("content_base64") or "")
    try:
        raw = base64.b64decode(content_b64)
    except Exception:
        raise ValueError("content_base64 is not valid base64")
    if len(raw) > _MAX_BYTES:
        raise ValueError(f"Attachment exceeds 5 MB limit ({len(raw)} bytes)")

    attachment = request.env["ir.attachment"].with_user(user).create({
        "name": str(params["filename"]),
        "mimetype": str(params.get("mimetype") or "application/octet-stream"),
        "res_model": "project.task",
        "res_id": task.id,
        "datas": content_b64,
    })
    return {"id": attachment.id, "name": attachment.name, "message": "Attachment uploaded"}


def add_followers(user, params: dict[str, Any]) -> dict[str, Any]:
    """Subscribe one or more partners as followers of a project task.

    partner_emails: list of email addresses (or Odoo logins) to add.
    Each is resolved to res.partner via email match; unresolved emails are skipped.
    Followers receive Odoo chatter notifications on all future task updates.
    """
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")

    partner_ids: list[int] = []
    for email in (params.get("partner_emails") or []):
        email = str(email).strip()
        if not email:
            continue
        partner = request.env["res.partner"].sudo().search(
            ["|", ("email", "=", email), ("user_ids.login", "=", email)], limit=1
        )
        if not partner:
            # Log server-side only — do not expose existence information to callers.
            _logger.warning("add_followers: no partner found for %r (task %s)", email, params["task_id"])
        elif not _is_internal_user(partner):
            # Only subscribe internal users; reject portal/external partners to prevent
            # leaking task content to accounts outside the organisation.
            _logger.warning("add_followers: rejected external partner %r (task %s)", email, params["task_id"])
        else:
            partner_ids.append(partner.id)

    if partner_ids:
        task.message_subscribe(partner_ids=partner_ids)

    return {"id": task.id, "added": len(partner_ids), "message": "Followers updated"}


def remove_followers(user, params: dict[str, Any]) -> dict[str, Any]:
    """Unsubscribe one or more partners from a project task's followers.

    partner_emails: list of email addresses (or Odoo logins) to remove.
    """
    task = request.env["project.task"].with_user(user).browse(int(params["task_id"])).exists()
    if not task:
        raise ValueError("Project task not found or not visible")

    partner_ids: list[int] = []
    for email in (params.get("partner_emails") or []):
        email = str(email).strip()
        if not email:
            continue
        partner = request.env["res.partner"].sudo().search(
            ["|", ("email", "=", email), ("user_ids.login", "=", email)], limit=1
        )
        if partner:
            partner_ids.append(partner.id)

    if partner_ids:
        task.message_unsubscribe(partner_ids=partner_ids)

    return {"id": task.id, "removed": len(partner_ids), "message": "Followers removed"}


def set_task_state(user, params: dict[str, Any]) -> dict[str, Any]:
    """Set the personal state (status pill) on a project task.

    Distinct from the Kanban stage column (stage_id, changed via move_task_stage):
    state is the per-user status indicator — in_progress / changes_requested /
    approved / cancelled / done.
    """
    task_id = int(params.get("task_id") or 0)
    state = str(params.get("state") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    if not state:
        raise ValueError("state is required")
    odoo_code = _resolve_state_code(user, state)
    task = request.env["project.task"].with_user(user).browse(task_id).exists()
    if not task:
        raise ValueError("Project task not found or not visible")
    task.write({"state": odoo_code})
    return {"id": task.id, "state": state, "message": f"Task personal state set to '{state}'"}


def get_tasks_bulk(user, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch full detail for multiple project tasks in a single Odoo read() call.

    Caps at 100 IDs. Tasks the caller cannot see are silently dropped by exists().
    Does not include comments/attachments/followers — call get_task individually
    for those, since they require per-record chatter queries.
    """
    raw_ids = params.get("task_ids") or []
    if not raw_ids:
        raise ValueError("task_ids is required and must be a non-empty list")
    task_ids = [int(i) for i in raw_ids[:_BULK_TASK_MAX]]

    Task = request.env["project.task"].with_user(user)
    records = Task.browse(task_ids).exists().read(TASK_DETAIL_FIELDS)
    if not records:
        return {"tasks": [], "count": 0}

    _enrich_user_ids(user, records)

    tag_id_set: set[int] = set()
    for r in records:
        tag_id_set.update(r.get("tag_ids") or [])
    if tag_id_set:
        tag_rows = request.env["project.tags"].sudo().browse(list(tag_id_set)).read(["id", "name"])
        tag_map = {t["id"]: t for t in tag_rows}
        for r in records:
            r["tag_ids"] = [tag_map[tid] for tid in (r.get("tag_ids") or []) if tid in tag_map]

    items = compact_records(records)
    return {"tasks": items, "count": len(items)}
