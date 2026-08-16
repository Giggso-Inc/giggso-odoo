"""Unit tests for project_actions — create_task and list_tasks.

create_task covers:
  - assignee_email resolves to a valid user → task created with that user
  - assignee_email provided but no matching user → ValueError raised
  - no assignee_email → task assigned to the authenticated actor
  - user_ids already in values → not overridden by the actor fallback

list_tasks covers:
  - no filters → empty domain
  - filter by stage_id → ("stage_id", "=", id) in domain
  - filter by stage_name → ("stage_id.name", "ilike", name) in domain
  - filter by assignee_email → OR clause on login + email in domain
  - filter by created_after → ("create_date", ">=", date) in domain
  - filter by state → ("state", "=", value) in domain
  - create_date present in TASK_FIELDS constant

Odoo's ORM is mocked; no live Odoo instance is required.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, call, patch

import pytest

# conftest.py has already loaded the module — grab it from sys.modules.
project_actions = sys.modules["odoo_mcp_connector.controllers.project_actions"]
create_task = project_actions.create_task
list_tasks = project_actions.list_tasks


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
