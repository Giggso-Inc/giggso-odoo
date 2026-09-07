"""Unit tests for activity_actions.list_activities and mark_activity_done.

Covers:
  - list_activities on a lead / partner returns a formatted list
  - list_activities with no activities returns an empty list (not an error)
  - mark_activity_done success calls action_feedback
  - mark_activity_done on a missing activity raises ValueError

Odoo's ORM is mocked; no live Odoo instance is required.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# conftest.py has already loaded the module — grab it from sys.modules.
activity_actions = sys.modules["odoo_mcp_connector.controllers.activity_actions"]
list_activities = activity_actions.list_activities
mark_activity_done = activity_actions.mark_activity_done


def _make_user(uid: int = 1) -> MagicMock:
    u = MagicMock(name=f"user_{uid}")
    u.id = uid
    return u


def _patch_list_request(rows=None):
    mock_request = MagicMock(name="request")
    activity_env = MagicMock()
    activity_env.with_user.return_value.search_read.return_value = rows or []
    mock_request.env.__getitem__.side_effect = (
        lambda model: activity_env if model == "mail.activity" else MagicMock()
    )
    ctx = patch.object(activity_actions, "request", mock_request)
    return ctx


class TestListActivities:
    def test_list_activities_on_lead_returns_formatted_rows(self):
        rows = [{
            "id": 1, "activity_type_id": [3, "Call"], "summary": "Follow up",
            "date_deadline": "2026-09-10", "user_id": [5, "Alice"],
            "note": "Discuss pricing", "state": "planned",
        }]
        ctx = _patch_list_request(rows=rows)
        with ctx:
            result = list_activities(_make_user(), {"res_model": "crm.lead", "res_id": 42})
        assert len(result["activities"]) == 1
        item = result["activities"][0]
        assert item["type"] == {"id": 3, "name": "Call"}
        assert item["assigned_to"] == {"id": 5, "name": "Alice"}
        assert item["summary"] == "Follow up"

    def test_list_activities_on_partner_returns_rows(self):
        rows = [{
            "id": 2, "activity_type_id": [1, "To-Do"], "summary": None,
            "date_deadline": "2026-09-11", "user_id": [5, "Alice"],
            "note": None, "state": "planned",
        }]
        ctx = _patch_list_request(rows=rows)
        with ctx:
            result = list_activities(_make_user(), {"res_model": "res.partner", "res_id": 10})
        assert len(result["activities"]) == 1

    def test_no_activities_returns_empty_list(self):
        ctx = _patch_list_request(rows=[])
        with ctx:
            result = list_activities(_make_user(), {"res_model": "crm.lead", "res_id": 42})
        assert result["activities"] == []

    def test_missing_res_model_raises(self):
        ctx = _patch_list_request()
        with ctx:
            with pytest.raises(ValueError, match="res_model is required"):
                list_activities(_make_user(), {"res_id": 42})

    def test_missing_res_id_raises(self):
        ctx = _patch_list_request()
        with ctx:
            with pytest.raises(ValueError, match="res_id is required"):
                list_activities(_make_user(), {"res_model": "crm.lead"})


def _patch_mark_done_request(activity=None):
    mock_request = MagicMock(name="request")
    activity_env = MagicMock()
    activity_env.with_user.return_value.browse.return_value.exists.return_value = (
        activity if activity is not None else MagicMock(__bool__=MagicMock(return_value=False))
    )
    mock_request.env.__getitem__.side_effect = (
        lambda model: activity_env if model == "mail.activity" else MagicMock()
    )
    ctx = patch.object(activity_actions, "request", mock_request)
    return ctx


class TestMarkActivityDone:
    def test_success_calls_action_feedback(self):
        activity = MagicMock()
        activity.__bool__ = MagicMock(return_value=True)
        ctx = _patch_mark_done_request(activity=activity)
        with ctx:
            result = mark_activity_done(_make_user(), {"activity_id": 1, "feedback": "Handled"})
        assert result == {"success": True}
        activity.action_feedback.assert_called_once_with(feedback="Handled")

    def test_missing_activity_raises(self):
        ctx = _patch_mark_done_request(activity=None)
        with ctx:
            with pytest.raises(ValueError, match="not found or not visible"):
                mark_activity_done(_make_user(), {"activity_id": 999})

    def test_missing_activity_id_raises(self):
        ctx = _patch_mark_done_request(activity=None)
        with ctx:
            with pytest.raises(ValueError, match="activity_id is required"):
                mark_activity_done(_make_user(), {})
