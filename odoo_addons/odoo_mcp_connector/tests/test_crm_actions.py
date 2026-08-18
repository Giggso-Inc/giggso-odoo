"""Unit tests for crm_actions.search_opportunities domain construction.

Covers:
  - no query → empty domain (unfiltered)
  - query matches opportunity title via ilike (name)
  - query matches customer email via =ilike (exact, case-insensitive)
  - query matches contact name via ilike
  - all three OR leaves are present in the domain when a query is given
  - case-insensitive email: upper-cased query still produces =ilike clause

Odoo's ORM is mocked; no live Odoo instance is required.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# conftest.py has already loaded the module — grab it from sys.modules.
crm_actions = sys.modules["odoo_mcp_connector.controllers.crm_actions"]
search_opportunities = crm_actions.search_opportunities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(uid: int = 1) -> MagicMock:
    u = MagicMock(name=f"user_{uid}")
    u.id = uid
    return u


def _patch_crm_request(records=None):
    """Patch request.env for search_opportunities. Returns (ctx, captured)."""
    mock_request = MagicMock(name="request")
    captured: dict = {}

    crm_env = MagicMock()

    def fake_search_read(domain, fields, limit=20, order="write_date desc"):
        captured["domain"] = list(domain)
        return records or []

    crm_env.with_user.return_value.search_read.side_effect = fake_search_read
    mock_request.env.__getitem__.side_effect = lambda model: crm_env if model == "crm.lead" else MagicMock()

    ctx = patch.object(crm_actions, "request", mock_request)
    return ctx, captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchOpportunitiesDomain:
    def _run(self, params):
        ctx, captured = _patch_crm_request()
        with ctx:
            search_opportunities(_make_user(), params)
        return captured.get("domain", [])

    def test_no_query_produces_empty_domain(self):
        domain = self._run({})
        assert domain == []

    def test_empty_string_query_produces_empty_domain(self):
        domain = self._run({"query": ""})
        assert domain == []

    def test_query_includes_name_ilike(self):
        domain = self._run({"query": "Acme deal"})
        assert ("name", "ilike", "Acme deal") in domain

    def test_query_includes_email_from_ilike(self):
        domain = self._run({"query": "alice@example.com"})
        assert ("email_from", "=ilike", "alice@example.com") in domain

    def test_email_from_uses_ilike_not_plain_equals(self):
        # Must be =ilike (case-insensitive exact), not = (case-sensitive).
        domain = self._run({"query": "alice@example.com"})
        assert ("email_from", "=", "alice@example.com") not in domain, (
            "email_from must use =ilike, not = — plain = is case-sensitive in Postgres"
        )

    def test_query_includes_contact_name_ilike(self):
        domain = self._run({"query": "Alice"})
        assert ("contact_name", "ilike", "Alice") in domain

    def test_two_or_operators_present_for_three_leaves(self):
        # Odoo needs two "|" operators to OR three leaves.
        domain = self._run({"query": "test"})
        assert domain.count("|") == 2

    def test_uppercase_email_uses_ilike_operator(self):
        # =ilike is case-insensitive so John@Example.com should still be emitted
        # as an =ilike clause (the matching happens DB-side).
        domain = self._run({"query": "JOHN@EXAMPLE.COM"})
        assert ("email_from", "=ilike", "JOHN@EXAMPLE.COM") in domain

    def test_returns_list(self):
        ctx, _ = _patch_crm_request(records=[{"id": 1, "name": "Deal"}])
        with ctx:
            result = search_opportunities(_make_user(), {"query": "Deal"})
        assert isinstance(result, list)
