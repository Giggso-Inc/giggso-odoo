"""Unit tests for project_actions — create_task, list_tasks, and security guards.

create_task covers:
  - assignee_email resolves to a valid user → task created with that user
  - assignee_email provided but no matching user → ValueError raised
  - no assignee_email → task assigned to the authenticated actor
  - user_ids already in values → not overridden by the actor fallback
  - parent_id resolves → set on task; inaccessible parent → ValueError

list_tasks covers:
  - no filters → empty domain
  - filter by stage_id → ("stage_id", "=", id) in domain
  - filter by stage_name → ("stage_id.name", "ilike", name) in domain
  - filter by assignee_email → OR clause on login + email in domain
  - filter by created_after → ("create_date", ">=", date) in domain
  - filter by state → ("state", "=", value) in domain
  - create_date present in TASK_FIELDS constant

add_followers security covers:
  - external (portal) partner is silently rejected — not subscribed
  - unknown email is skipped — response never exposes not_found list
  - internal user is subscribed normally

add_comment security covers:
  - external partner email is excluded from partner_ids passed to message_post

get_attachment covers:
  - text file returns text_content; binary file returns content_base64
  - file over 5 MB is rejected

attach_file covers:
  - invalid base64 raises ValueError

parent_id access-check covers:
  - inaccessible parent in update_task raises ValueError

Odoo's ORM is mocked; no live Odoo instance is required.
"""
from __future__ import annotations

import base64
import sys
from unittest.mock import MagicMock, call, patch

import pytest

# conftest.py has already loaded the module — grab it from sys.modules.
project_actions = sys.modules["odoo_mcp_connector.controllers.project_actions"]
create_task = project_actions.create_task
list_tasks = project_actions.list_tasks
add_followers = project_actions.add_followers
add_comment = project_actions.add_comment
get_attachment = project_actions.get_attachment
attach_file = project_actions.attach_file
update_task = project_actions.update_task
set_task_state = project_actions.set_task_state
get_tasks_bulk = project_actions.get_tasks_bulk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(uid: int = 10) -> MagicMock:
    """Return a minimal mock that looks like an Odoo res.users record."""
    u = MagicMock(name=f"user_{uid}")
    u.id = uid
    return u


def _make_task(tid: int = 42, name: str = "Test Task") -> MagicMock:
    t = MagicMock(name=f"task_{tid}")
    t.id = tid
    t.name = name
    return t


def _patch_request(assignee=None, task=None):
    """
    Return a context manager that patches odoo.http.request.env so that:
      - res.users.sudo().search() returns `assignee` (a recordset mock)
      - project.task.with_user(user).create() returns `task`
    """
    mock_request = MagicMock(name="request")

    # Recordset truthiness: an empty recordset is falsy in Odoo.
    users_env = MagicMock()
    if assignee is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        users_env.sudo.return_value.search.return_value = empty
    else:
        found = MagicMock()
        found.__bool__ = MagicMock(return_value=True)
        found.id = assignee.id
        users_env.sudo.return_value.search.return_value = found

    task_env = MagicMock()
    task_env.with_user.return_value.create.return_value = task or _make_task()

    # side_effect on __getitem__ is called with just the key (no self).
    def env_getitem(model):
        if model == "res.users":
            return users_env
        if model == "project.task":
            return task_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    return patch.object(project_actions, "request", mock_request), mock_request


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_assignee_email_resolved_to_user(self):
        actor = _make_user(uid=5)
        assignee = _make_user(uid=99)
        task = _make_task(tid=1, name="Assigned Task")

        ctx, mock_request = _patch_request(assignee=assignee, task=task)
        with ctx:
            result = create_task(
                actor,
                {
                    "values": {"project_id": 10, "name": "Assigned Task"},
                    "assignee_email": "bob@example.com",
                },
            )

        assert result["id"] == 1
        assert result["name"] == "Assigned Task"
        # The task was created with the assignee's id in user_ids.
        create_call_kwargs = mock_request.env["project.task"].with_user.return_value.create.call_args
        vals_passed = create_call_kwargs[0][0]
        assert (4, 99) in vals_passed["user_ids"]

    def test_assignee_email_not_found_raises_value_error(self):
        actor = _make_user(uid=5)

        ctx, _ = _patch_request(assignee=None)
        with ctx:
            with pytest.raises(ValueError, match="No active Odoo user found for assignee"):
                create_task(
                    actor,
                    {
                        "values": {"project_id": 10, "name": "Task"},
                        "assignee_email": "ghost@example.com",
                    },
                )

    def test_no_assignee_email_defaults_to_actor(self):
        actor = _make_user(uid=7)
        task = _make_task(tid=2)

        ctx, mock_request = _patch_request(task=task)
        with ctx:
            result = create_task(
                actor,
                {"values": {"project_id": 10, "name": "My Task"}},
            )

        assert result["id"] == 2
        vals_passed = mock_request.env["project.task"].with_user.return_value.create.call_args[0][0]
        assert (4, 7) in vals_passed["user_ids"]

    def test_user_ids_in_values_not_overridden_by_actor(self):
        actor = _make_user(uid=7)
        task = _make_task(tid=3)
        explicit_user_ids = [(4, 55)]

        ctx, mock_request = _patch_request(task=task)
        with ctx:
            create_task(
                actor,
                {"values": {"project_id": 10, "name": "Task", "user_ids": explicit_user_ids}},
            )

        vals_passed = mock_request.env["project.task"].with_user.return_value.create.call_args[0][0]
        assert vals_passed["user_ids"] == explicit_user_ids

    def test_empty_assignee_email_string_treated_as_absent(self):
        actor = _make_user(uid=8)
        task = _make_task(tid=4)

        ctx, mock_request = _patch_request(task=task)
        with ctx:
            create_task(
                actor,
                {
                    "values": {"project_id": 10, "name": "Task"},
                    "assignee_email": "   ",   # whitespace only → stripped to ""
                },
            )

        vals_passed = mock_request.env["project.task"].with_user.return_value.create.call_args[0][0]
        # Falls back to actor, no res.users search was made.
        assert (4, 8) in vals_passed["user_ids"]
        mock_request.env["res.users"].sudo.return_value.search.assert_not_called()

    def test_return_value_includes_name(self):
        actor = _make_user(uid=5)
        task = _make_task(tid=10, name="Named Task")

        ctx, _ = _patch_request(task=task)
        with ctx:
            result = create_task(actor, {"values": {"project_id": 1, "name": "Named Task"}})

        assert result["name"] == "Named Task"
        assert result["message"] == "Project task created"


# ---------------------------------------------------------------------------
# list_tasks filter tests
# ---------------------------------------------------------------------------

def _patch_list_request(records=None):
    """Patch request.env for list_tasks. Returns (ctx, mock_request, captured_domain)."""
    mock_request = MagicMock(name="request")
    captured = {}

    task_env = MagicMock()

    def fake_search_read(domain, fields, limit=30, order="write_date desc"):
        captured["domain"] = list(domain)
        return records or []

    task_env.with_user.return_value.search_read.side_effect = fake_search_read

    def env_getitem(model):
        if model == "project.task":
            return task_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, mock_request, captured


class TestListTasksFilters:
    def _run(self, params):
        """Run list_tasks with given params and return the captured ORM domain."""
        ctx, _, captured = _patch_list_request()
        with ctx:
            list_tasks(_make_user(), params)
        return captured.get("domain", [])

    def test_no_filters_produces_empty_domain(self):
        domain = self._run({})
        assert domain == []

    def test_filter_by_stage_id(self):
        domain = self._run({"stage_id": 5})
        assert ("stage_id", "=", 5) in domain

    def test_filter_by_stage_name(self):
        domain = self._run({"stage_name": "In Progress"})
        assert ("stage_id.name", "ilike", "In Progress") in domain

    def test_stage_id_takes_precedence_over_stage_name(self):
        domain = self._run({"stage_id": 3, "stage_name": "In Progress"})
        assert ("stage_id", "=", 3) in domain
        assert ("stage_id.name", "ilike", "In Progress") not in domain

    def test_filter_by_assignee_email(self):
        domain = self._run({"assignee_email": "alice@example.com"})
        assert "|" in domain
        assert ("user_ids.login", "=", "alice@example.com") in domain
        assert ("user_ids.email", "=", "alice@example.com") in domain

    def test_filter_by_created_after(self):
        domain = self._run({"created_after": "2026-07-29"})
        assert ("create_date", ">=", "2026-07-29") in domain

    def test_filter_by_created_before(self):
        domain = self._run({"created_before": "2026-07-30"})
        assert ("create_date", "<=", "2026-07-30") in domain

    def test_filter_by_state(self):
        domain = self._run({"state": "in_progress"})
        assert ("state", "=", "in_progress") in domain

    def test_multiple_filters_combined(self):
        domain = self._run({
            "project_id": 22,
            "stage_name": "Done",
            "assignee_email": "bob@example.com",
            "created_after": "2026-07-01",
        })
        assert ("project_id", "=", 22) in domain
        assert ("stage_id.name", "ilike", "Done") in domain
        assert ("create_date", ">=", "2026-07-01") in domain
        assert "|" in domain

    def test_create_date_in_task_fields_constant(self):
        assert "create_date" in project_actions.TASK_FIELDS

    def test_returns_dict_with_tasks_key(self):
        ctx, _, _ = _patch_list_request(records=[])
        with ctx:
            result = list_tasks(_make_user(), {})
        assert isinstance(result, dict)
        assert "tasks" in result
        assert "count" in result
        assert "truncated" in result

    def test_truncated_false_when_under_limit(self):
        ctx, _, _ = _patch_list_request(records=[{"id": 1}])
        with ctx:
            result = list_tasks(_make_user(), {"limit": 30})
        assert result["truncated"] is False
        assert result["count"] == 1

    def test_truncated_true_when_at_limit(self):
        # Return exactly `limit` rows — truncated should be True.
        rows = [{"id": i} for i in range(5)]
        ctx, _, _ = _patch_list_request(records=rows)
        with ctx:
            result = list_tasks(_make_user(), {"limit": 5})
        assert result["truncated"] is True

    def test_parent_id_in_task_fields(self):
        assert "parent_id" in project_actions.TASK_FIELDS

    def test_filter_by_created_by_email(self):
        domain = self._run({"created_by_email": "dev@example.com"})
        assert "|" in domain
        assert ("create_uid.login", "=", "dev@example.com") in domain
        assert ("create_uid.email", "=", "dev@example.com") in domain


# ---------------------------------------------------------------------------
# parent_id access-check tests
# ---------------------------------------------------------------------------

def _patch_request_with_parent(parent_task=None):
    """Patch request.env for create_task / update_task with parent task control."""
    mock_request = MagicMock(name="request")
    captured = {}

    users_env = MagicMock()
    empty_user = MagicMock()
    empty_user.__bool__ = MagicMock(return_value=False)
    users_env.sudo.return_value.search.return_value = empty_user

    task_env = MagicMock()
    created = _make_task(tid=99)
    task_env.with_user.return_value.create.return_value = created

    # Parent browse — return falsy when parent is None (inaccessible)
    parent_browse = MagicMock()
    parent_browse.exists.return_value = parent_task  # None → falsy, MagicMock → truthy
    if parent_task is None:
        parent_browse.exists.return_value = MagicMock(__bool__=MagicMock(return_value=False))
    task_env.with_user.return_value.browse.return_value = parent_browse

    def env_getitem(model):
        if model == "res.users":
            return users_env
        if model == "project.task":
            return task_env
        if model == "project.tags":
            return MagicMock()
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, mock_request


class TestParentIdAccessCheck:
    def test_inaccessible_parent_in_create_task_raises(self):
        actor = _make_user(uid=5)
        ctx, _ = _patch_request_with_parent(parent_task=None)
        with ctx:
            with pytest.raises(ValueError, match="Parent task not found or not visible"):
                create_task(
                    actor,
                    {"values": {"project_id": 1, "name": "Sub"}, "parent_id": 9999},
                )

    def test_accessible_parent_in_create_task_sets_field(self):
        actor = _make_user(uid=5)
        parent = _make_task(tid=10)
        ctx, mock_request = _patch_request_with_parent(parent_task=parent)
        with ctx:
            result = create_task(
                actor,
                {"values": {"project_id": 1, "name": "Sub"}, "parent_id": 10},
            )
        vals = mock_request.env["project.task"].with_user.return_value.create.call_args[0][0]
        assert vals.get("parent_id") == parent.id

    def test_inaccessible_parent_in_update_task_raises(self):
        actor = _make_user(uid=5)
        # update_task first browses the task itself (task_id), then browses parent_id.
        mock_request = MagicMock(name="request")
        existing_task = _make_task(tid=42)

        call_count = {"n": 0}

        def browse_side_effect(record_id):
            call_count["n"] += 1
            m = MagicMock()
            if call_count["n"] == 1:
                # First browse: the task itself — must exist
                m.exists.return_value = existing_task
            else:
                # Second browse: parent — must be inaccessible
                inaccessible = MagicMock()
                inaccessible.__bool__ = MagicMock(return_value=False)
                m.exists.return_value = inaccessible
            return m

        task_env = MagicMock()
        task_env.with_user.return_value.browse.side_effect = browse_side_effect

        mock_request.env.__getitem__.side_effect = lambda model: task_env if model == "project.task" else MagicMock()

        with patch.object(project_actions, "request", mock_request):
            with pytest.raises(ValueError, match="Parent task not found or not visible"):
                update_task(
                    actor,
                    {"task_id": 42, "values": {"name": "Updated"}, "parent_id": 9999},
                )


# ---------------------------------------------------------------------------
# add_followers security tests
# ---------------------------------------------------------------------------

def _make_partner(pid: int = 1, is_internal: bool = True) -> MagicMock:
    partner = MagicMock(name=f"partner_{pid}")
    partner.id = pid
    user = MagicMock()
    user.active = True
    user.share = not is_internal  # share=True → portal/external
    partner.user_ids.filtered.return_value = [user] if is_internal else []
    partner.__bool__ = MagicMock(return_value=True)
    return partner


def _patch_followers_request(task_exists=True, partner=None):
    mock_request = MagicMock(name="request")

    task_mock = MagicMock()
    task_mock.__bool__ = MagicMock(return_value=task_exists)
    task_mock.id = 42

    task_env = MagicMock()
    task_env.with_user.return_value.browse.return_value.exists.return_value = task_mock if task_exists else MagicMock(__bool__=MagicMock(return_value=False))

    partner_env = MagicMock()
    if partner is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.sudo.return_value.search.return_value = empty
    else:
        partner_env.sudo.return_value.search.return_value = partner

    def env_getitem(model):
        if model == "project.task":
            return task_env
        if model == "res.partner":
            return partner_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, task_mock


class TestAddFollowersSecurity:
    def test_internal_user_is_subscribed(self):
        partner = _make_partner(pid=55, is_internal=True)
        ctx, task_mock = _patch_followers_request(partner=partner)
        with ctx:
            result = add_followers(_make_user(), {"task_id": 42, "partner_emails": ["alice@example.com"]})
        assert result["added"] == 1
        task_mock.message_subscribe.assert_called_once_with(partner_ids=[55])

    def test_external_partner_is_rejected_silently(self):
        partner = _make_partner(pid=77, is_internal=False)
        ctx, task_mock = _patch_followers_request(partner=partner)
        with ctx:
            result = add_followers(_make_user(), {"task_id": 42, "partner_emails": ["external@vendor.com"]})
        assert result["added"] == 0
        task_mock.message_subscribe.assert_not_called()

    def test_unknown_email_not_exposed_in_response(self):
        ctx, task_mock = _patch_followers_request(partner=None)
        with ctx:
            result = add_followers(_make_user(), {"task_id": 42, "partner_emails": ["ghost@example.com"]})
        assert result["added"] == 0
        assert "not_found" not in result, "Enumeration oracle: not_found must not be in the response"
        task_mock.message_subscribe.assert_not_called()


# ---------------------------------------------------------------------------
# add_comment security tests
# ---------------------------------------------------------------------------

def _patch_comment_request(task_exists=True, partner=None):
    mock_request = MagicMock(name="request")

    task_mock = MagicMock()
    task_mock.__bool__ = MagicMock(return_value=task_exists)
    task_mock.id = 42

    task_env = MagicMock()
    task_env.with_user.return_value.browse.return_value.exists.return_value = task_mock if task_exists else MagicMock(__bool__=MagicMock(return_value=False))

    partner_env = MagicMock()
    if partner is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.sudo.return_value.search.return_value = empty
    else:
        partner_env.sudo.return_value.search.return_value = partner

    def env_getitem(model):
        if model == "project.task":
            return task_env
        if model == "res.partner":
            return partner_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, task_mock


class TestAddCommentSecurity:
    def test_external_partner_excluded_from_notifications(self):
        partner = _make_partner(pid=88, is_internal=False)
        ctx, task_mock = _patch_comment_request(partner=partner)
        with ctx:
            result = add_comment(
                _make_user(),
                {"task_id": 42, "comment": "Hello", "partner_emails": ["external@vendor.com"]},
            )
        # message_post must be called with empty partner_ids — external excluded.
        call_kwargs = task_mock.message_post.call_args[1]
        assert call_kwargs["partner_ids"] == []
        assert result["notified"] == 0

    def test_internal_user_included_in_notifications(self):
        partner = _make_partner(pid=99, is_internal=True)
        ctx, task_mock = _patch_comment_request(partner=partner)
        with ctx:
            result = add_comment(
                _make_user(),
                {"task_id": 42, "comment": "Hello", "partner_emails": ["alice@example.com"]},
            )
        call_kwargs = task_mock.message_post.call_args[1]
        assert 99 in call_kwargs["partner_ids"]
        assert result["notified"] == 1


# ---------------------------------------------------------------------------
# get_attachment tests
# ---------------------------------------------------------------------------

def _patch_attachment_request(attachment=None):
    mock_request = MagicMock(name="request")
    attach_env = MagicMock()
    attach_env.with_user.return_value.browse.return_value.exists.return_value = attachment
    mock_request.env.__getitem__.side_effect = lambda model: attach_env if model == "ir.attachment" else MagicMock()
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx


def _make_attachment(aid: int = 1, mimetype: str = "text/plain", content: bytes = b"hello", file_size: int = 5):
    a = MagicMock(name=f"attachment_{aid}")
    a.id = aid
    a.name = "file.txt"
    a.mimetype = mimetype
    a.file_size = file_size
    a.datas = base64.b64encode(content).decode()
    a.__bool__ = MagicMock(return_value=True)
    return a


class TestGetAttachment:
    def test_text_file_returns_text_content(self):
        att = _make_attachment(mimetype="text/plain", content=b"# Title\nBody text")
        ctx = _patch_attachment_request(attachment=att)
        with ctx:
            result = get_attachment(_make_user(), {"attachment_id": 1})
        assert "text_content" in result
        assert result["text_content"] == "# Title\nBody text"
        assert "content_base64" not in result

    def test_binary_file_returns_base64(self):
        att = _make_attachment(mimetype="application/pdf", content=b"\x25\x50\x44\x46")
        ctx = _patch_attachment_request(attachment=att)
        with ctx:
            result = get_attachment(_make_user(), {"attachment_id": 1})
        assert "content_base64" in result
        assert "text_content" not in result

    def test_file_over_5mb_is_rejected(self):
        att = _make_attachment(file_size=6 * 1024 * 1024)
        ctx = _patch_attachment_request(attachment=att)
        with ctx:
            with pytest.raises(ValueError, match="5 MB"):
                get_attachment(_make_user(), {"attachment_id": 1})

    def test_missing_attachment_raises(self):
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        ctx = _patch_attachment_request(attachment=empty)
        with ctx:
            with pytest.raises(ValueError, match="not found"):
                get_attachment(_make_user(), {"attachment_id": 9999})


# ---------------------------------------------------------------------------
# attach_file tests
# ---------------------------------------------------------------------------

def _patch_attach_file_request(task_exists=True):
    mock_request = MagicMock(name="request")

    task_mock = MagicMock()
    task_mock.__bool__ = MagicMock(return_value=task_exists)
    task_mock.id = 42

    task_env = MagicMock()
    task_env.with_user.return_value.browse.return_value.exists.return_value = task_mock if task_exists else MagicMock(__bool__=MagicMock(return_value=False))

    attach_env = MagicMock()
    created = MagicMock()
    created.id = 101
    created.name = "report.pdf"
    attach_env.with_user.return_value.create.return_value = created

    def env_getitem(model):
        if model == "project.task":
            return task_env
        if model == "ir.attachment":
            return attach_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx


class TestAttachFile:
    def test_invalid_base64_raises(self):
        ctx = _patch_attach_file_request()
        with ctx:
            with pytest.raises(ValueError, match="not valid base64"):
                attach_file(_make_user(), {
                    "task_id": 42,
                    "filename": "bad.txt",
                    "content_base64": "!!!not-base64!!!",
                })

    def test_valid_upload_returns_id(self):
        content_b64 = base64.b64encode(b"PDF content").decode()
        ctx = _patch_attach_file_request()
        with ctx:
            result = attach_file(_make_user(), {
                "task_id": 42,
                "filename": "report.pdf",
                "mimetype": "application/pdf",
                "content_base64": content_b64,
            })
        assert result["id"] == 101
        assert result["message"] == "Attachment uploaded"


# ---------------------------------------------------------------------------
# list_tasks field enrichment tests
# ---------------------------------------------------------------------------

class TestListTasksEnrichment:
    def test_description_in_task_fields_constant(self):
        assert "description" in project_actions.TASK_FIELDS

    def test_write_date_in_task_fields_constant(self):
        assert "write_date" in project_actions.TASK_FIELDS

    def test_user_ids_enriched_to_name_email_dicts(self):
        mock_request = MagicMock(name="request")
        task_env = MagicMock()
        rows = [{"id": 1, "user_ids": [3, 7]}]
        task_env.with_user.return_value.search_read.return_value = rows

        users_env = MagicMock()
        users_env.with_user.return_value.browse.return_value.read.return_value = [
            {"id": 3, "name": "Alice", "email": "alice@example.com"},
            {"id": 7, "name": "Bob", "email": "bob@example.com"},
        ]

        def env_getitem(model):
            if model == "project.task":
                return task_env
            if model == "res.users":
                return users_env
            return MagicMock()

        mock_request.env.__getitem__.side_effect = env_getitem
        with patch.object(project_actions, "request", mock_request):
            result = list_tasks(_make_user(), {})

        task = result["tasks"][0]
        assert task["user_ids"] == [
            {"id": 3, "name": "Alice", "email": "alice@example.com"},
            {"id": 7, "name": "Bob", "email": "bob@example.com"},
        ]

    def test_no_user_ids_skips_enrichment_query(self):
        mock_request = MagicMock(name="request")
        task_env = MagicMock()
        task_env.with_user.return_value.search_read.return_value = [{"id": 1}]
        users_env = MagicMock()

        def env_getitem(model):
            if model == "project.task":
                return task_env
            if model == "res.users":
                return users_env
            return MagicMock()

        mock_request.env.__getitem__.side_effect = env_getitem
        with patch.object(project_actions, "request", mock_request):
            list_tasks(_make_user(), {})

        users_env.with_user.return_value.browse.assert_not_called()


# ---------------------------------------------------------------------------
# set_task_state tests
# ---------------------------------------------------------------------------

def _patch_state_request(task_exists=True):
    mock_request = MagicMock(name="request")
    task_mock = MagicMock()
    task_mock.__bool__ = MagicMock(return_value=task_exists)
    task_mock.id = 42

    task_env = MagicMock()
    task_env.with_user.return_value.browse.return_value.exists.return_value = (
        task_mock if task_exists else MagicMock(__bool__=MagicMock(return_value=False))
    )
    mock_request.env.__getitem__.side_effect = (
        lambda model: task_env if model == "project.task" else MagicMock()
    )
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, task_mock


class TestSetTaskState:
    def test_valid_state_writes_field(self):
        ctx, task_mock = _patch_state_request()
        with ctx:
            result = set_task_state(_make_user(), {"task_id": 42, "state": "approved"})
        assert result["state"] == "approved"
        task_mock.write.assert_called_once_with({"state": "approved"})

    def test_invalid_state_raises(self):
        ctx, _ = _patch_state_request()
        with ctx:
            with pytest.raises(ValueError, match="Invalid state"):
                set_task_state(_make_user(), {"task_id": 42, "state": "bogus"})

    def test_invisible_task_raises(self):
        ctx, _ = _patch_state_request(task_exists=False)
        with ctx:
            with pytest.raises(ValueError, match="not found or not visible"):
                set_task_state(_make_user(), {"task_id": 999, "state": "done"})

    def test_missing_task_id_raises(self):
        ctx, _ = _patch_state_request()
        with ctx:
            with pytest.raises(ValueError, match="task_id is required"):
                set_task_state(_make_user(), {"state": "done"})


# ---------------------------------------------------------------------------
# get_tasks_bulk tests
# ---------------------------------------------------------------------------

def _patch_bulk_request(rows=None):
    mock_request = MagicMock(name="request")
    task_env = MagicMock()
    task_env.with_user.return_value.browse.return_value.exists.return_value.read.return_value = rows or []
    users_env = MagicMock()
    users_env.with_user.return_value.browse.return_value.read.return_value = []
    tags_env = MagicMock()
    tags_env.sudo.return_value.browse.return_value.read.return_value = []

    def env_getitem(model):
        if model == "project.task":
            return task_env
        if model == "res.users":
            return users_env
        if model == "project.tags":
            return tags_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(project_actions, "request", mock_request)
    return ctx, task_env


class TestGetTasksBulk:
    def test_two_visible_ids_returned(self):
        rows = [{"id": 1, "name": "Task A"}, {"id": 2, "name": "Task B"}]
        ctx, _ = _patch_bulk_request(rows=rows)
        with ctx:
            result = get_tasks_bulk(_make_user(), {"task_ids": [1, 2]})
        assert result["count"] == 2
        assert {t["id"] for t in result["tasks"]} == {1, 2}

    def test_ids_capped_at_100(self):
        ctx, task_env = _patch_bulk_request(rows=[])
        with ctx:
            get_tasks_bulk(_make_user(), {"task_ids": list(range(150))})
        browse_call_ids = task_env.with_user.return_value.browse.call_args[0][0]
        assert len(browse_call_ids) == 100

    def test_empty_list_raises(self):
        ctx, _ = _patch_bulk_request()
        with ctx:
            with pytest.raises(ValueError, match="non-empty list"):
                get_tasks_bulk(_make_user(), {"task_ids": []})

    def test_missing_task_ids_raises(self):
        ctx, _ = _patch_bulk_request()
        with ctx:
            with pytest.raises(ValueError, match="non-empty list"):
                get_tasks_bulk(_make_user(), {})

    def test_no_matching_records_returns_empty(self):
        ctx, _ = _patch_bulk_request(rows=[])
        with ctx:
            result = get_tasks_bulk(_make_user(), {"task_ids": [1, 2]})
        assert result == {"tasks": [], "count": 0}
