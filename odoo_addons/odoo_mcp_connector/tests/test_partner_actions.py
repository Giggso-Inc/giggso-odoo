"""Unit tests for partner_actions — find/create/enrich/find_or_enrich, activity, chatter.

Covers:
  find_partner_by_email: found / not found / case-insensitive match
  create_partner: minimal (name only) / full field set with country resolution
  enrich_partner: blank fields updated / populated fields skipped / not found
  find_or_enrich_partner: existing -> updated / no existing -> created
  partner_schedule_activity: created / invalid partner
  partner_post_message: success / missing body

Odoo's ORM is mocked; no live Odoo instance is required.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# conftest.py has already loaded the module — grab it from sys.modules.
partner_actions = sys.modules["odoo_mcp_connector.controllers.partner_actions"]
find_partner_by_email = partner_actions.find_partner_by_email
create_partner = partner_actions.create_partner
enrich_partner = partner_actions.enrich_partner
find_or_enrich_partner = partner_actions.find_or_enrich_partner
partner_schedule_activity = partner_actions.partner_schedule_activity
partner_post_message = partner_actions.partner_post_message


def _make_user(uid: int = 1) -> MagicMock:
    u = MagicMock(name=f"user_{uid}")
    u.id = uid
    return u


def _make_partner(pid: int = 1, **field_overrides) -> MagicMock:
    """Return a mock res.partner record with sensible blank defaults."""
    p = MagicMock(name=f"partner_{pid}")
    p.id = pid
    p.name = field_overrides.get("name", "Alice")
    p.email = field_overrides.get("email", False)
    p.phone = field_overrides.get("phone", False)
    p.mobile = field_overrides.get("mobile", False)
    p.function = field_overrides.get("function", False)
    p.street = field_overrides.get("street", False)
    p.city = field_overrides.get("city", False)
    p.zip = field_overrides.get("zip", False)
    p.website = field_overrides.get("website", False)
    p.state_id = field_overrides.get("state_id", False)
    p.country_id = field_overrides.get("country_id", False)
    p.parent_id = field_overrides.get("parent_id", False)
    p.is_company = field_overrides.get("is_company", False)
    p.__bool__ = MagicMock(return_value=True)
    return p


# ---------------------------------------------------------------------------
# find_partner_by_email
# ---------------------------------------------------------------------------

def _patch_find_request(found=None):
    mock_request = MagicMock(name="request")
    partner_env = MagicMock()
    if found is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.with_user.return_value.search.return_value = empty
    else:
        partner_env.with_user.return_value.search.return_value = found
    mock_request.env.__getitem__.side_effect = (
        lambda model: partner_env if model == "res.partner" else MagicMock()
    )
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx, partner_env


class TestFindPartnerByEmail:
    def test_found_returns_partner_dict(self):
        partner = _make_partner(pid=10, email="alice@example.com")
        ctx, _ = _patch_find_request(found=partner)
        with ctx:
            result = find_partner_by_email(_make_user(), {"email": "alice@example.com"})
        assert result["found"] is True
        assert result["partner"]["id"] == 10

    def test_not_found_returns_false(self):
        ctx, _ = _patch_find_request(found=None)
        with ctx:
            result = find_partner_by_email(_make_user(), {"email": "ghost@example.com"})
        assert result == {"found": False, "partner": None}

    def test_case_insensitive_search_uses_ilike(self):
        partner = _make_partner(pid=11, email="alice@example.com")
        ctx, partner_env = _patch_find_request(found=partner)
        with ctx:
            find_partner_by_email(_make_user(), {"email": "ALICE@EXAMPLE.COM"})
        search_domain = partner_env.with_user.return_value.search.call_args[0][0]
        assert ("email", "=ilike", "ALICE@EXAMPLE.COM") in search_domain

    def test_missing_email_raises(self):
        ctx, _ = _patch_find_request()
        with ctx:
            with pytest.raises(ValueError, match="email is required"):
                find_partner_by_email(_make_user(), {})


# ---------------------------------------------------------------------------
# create_partner
# ---------------------------------------------------------------------------

def _patch_create_request(created=None, country=None, state=None):
    mock_request = MagicMock(name="request")

    partner_env = MagicMock()
    partner_env.with_user.return_value.create.return_value = created or _make_partner(pid=1)

    country_env = MagicMock()
    if country is not None:
        country_env.with_user.return_value.search.return_value = country
    else:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        country_env.with_user.return_value.search.return_value = empty

    def env_getitem(model):
        if model == "res.partner":
            return partner_env
        if model == "res.country":
            return country_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx, partner_env


class TestCreatePartner:
    def test_minimal_name_only(self):
        created = _make_partner(pid=20, name="Bob")
        ctx, partner_env = _patch_create_request(created=created)
        with ctx:
            result = create_partner(_make_user(), {"name": "Bob"})
        assert result == {"id": 20, "name": "Bob"}

    def test_missing_name_raises(self):
        ctx, _ = _patch_create_request()
        with ctx:
            with pytest.raises(ValueError, match="name is required"):
                create_partner(_make_user(), {})

    def test_full_field_set_resolves_country(self):
        country = MagicMock()
        country.id = 233
        country.__bool__ = MagicMock(return_value=True)
        created = _make_partner(pid=21, name="Carol")
        ctx, partner_env = _patch_create_request(created=created, country=country)
        with ctx:
            create_partner(_make_user(), {
                "name": "Carol", "email": "carol@co.com", "phone": "123",
                "mobile": "456", "function": "CTO", "street": "1 Main St",
                "city": "Springfield", "zip_code": "90210",
                "country_name": "United States", "website": "https://co.com",
            })
        vals = partner_env.with_user.return_value.create.call_args[0][0]
        assert vals["country_id"] == 233
        assert vals["function"] == "CTO"
        assert vals["zip"] == "90210"


# ---------------------------------------------------------------------------
# enrich_partner
# ---------------------------------------------------------------------------

def _patch_enrich_request(record=None):
    mock_request = MagicMock(name="request")
    partner_env = MagicMock()
    if record is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.with_user.return_value.browse.return_value.exists.return_value = empty
    else:
        partner_env.with_user.return_value.browse.return_value.exists.return_value = record
    mock_request.env.__getitem__.side_effect = (
        lambda model: partner_env if model == "res.partner" else MagicMock()
    )
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx


class TestEnrichPartner:
    def test_blank_fields_are_updated(self):
        record = _make_partner(pid=30, phone=False, mobile=False)
        ctx = _patch_enrich_request(record=record)
        with ctx:
            result = enrich_partner(_make_user(), {
                "partner_id": 30, "phone": "111-222", "mobile": "333-444",
            })
        assert set(result["updated_fields"]) == {"phone", "mobile"}
        record.write.assert_called_once()
        written = record.write.call_args[0][0]
        assert written == {"phone": "111-222", "mobile": "333-444"}

    def test_populated_fields_are_skipped(self):
        record = _make_partner(pid=31, phone="already-set")
        ctx = _patch_enrich_request(record=record)
        with ctx:
            result = enrich_partner(_make_user(), {"partner_id": 31, "phone": "999-999"})
        assert "phone" in result["skipped_fields"]
        assert "phone" not in result["updated_fields"]

    def test_partner_not_found_raises(self):
        ctx = _patch_enrich_request(record=None)
        with ctx:
            with pytest.raises(ValueError, match="not found or access denied"):
                enrich_partner(_make_user(), {"partner_id": 999, "phone": "111"})

    def test_missing_partner_id_raises(self):
        ctx = _patch_enrich_request()
        with ctx:
            with pytest.raises(ValueError, match="partner_id is required"):
                enrich_partner(_make_user(), {})


# ---------------------------------------------------------------------------
# find_or_enrich_partner
# ---------------------------------------------------------------------------

def _patch_find_or_enrich_request(existing=None, created=None):
    mock_request = MagicMock(name="request")
    partner_env = MagicMock()

    if existing is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.with_user.return_value.search.return_value = empty
    else:
        partner_env.with_user.return_value.search.return_value = existing
        partner_env.with_user.return_value.browse.return_value.exists.return_value = existing

    partner_env.with_user.return_value.create.return_value = created or _make_partner(pid=99)

    mock_request.env.__getitem__.side_effect = (
        lambda model: partner_env if model == "res.partner" else MagicMock()
    )
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx


class TestFindOrEnrichPartner:
    def test_existing_email_triggers_update(self):
        existing = _make_partner(pid=40, email="dave@co.com", phone=False)
        ctx = _patch_find_or_enrich_request(existing=existing)
        with ctx:
            result = find_or_enrich_partner(_make_user(), {"email": "dave@co.com", "phone": "555"})
        assert result["action"] == "updated"
        assert result["partner_id"] == 40

    def test_no_existing_triggers_create(self):
        created = _make_partner(pid=41, name="Eve")
        ctx = _patch_find_or_enrich_request(existing=None, created=created)
        with ctx:
            result = find_or_enrich_partner(_make_user(), {"email": "eve@co.com", "name": "Eve"})
        assert result["action"] == "created"
        assert result["partner_id"] == 41

    def test_missing_email_raises(self):
        ctx = _patch_find_or_enrich_request()
        with ctx:
            with pytest.raises(ValueError, match="email is required"):
                find_or_enrich_partner(_make_user(), {})


# ---------------------------------------------------------------------------
# partner_schedule_activity
# ---------------------------------------------------------------------------

def _patch_schedule_activity_request(partner=None, activity_type=None, created_activity=None):
    mock_request = MagicMock(name="request")

    partner_env = MagicMock()
    if partner is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.with_user.return_value.browse.return_value.exists.return_value = empty
    else:
        partner_env.with_user.return_value.browse.return_value.exists.return_value = partner

    type_env = MagicMock()
    if activity_type is not None:
        type_env.with_user.return_value.search.return_value = activity_type
    else:
        empty_type = MagicMock()
        empty_type.__bool__ = MagicMock(return_value=False)
        type_env.with_user.return_value.search.return_value = empty_type

    activity_env = MagicMock()
    created = created_activity or MagicMock(id=777)
    activity_env.with_user.return_value.create.return_value = created

    def env_getitem(model):
        if model == "res.partner":
            return partner_env
        if model == "mail.activity.type":
            return type_env
        if model == "mail.activity":
            return activity_env
        return MagicMock()

    mock_request.env.__getitem__.side_effect = env_getitem
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx


class TestPartnerScheduleActivity:
    def test_activity_created(self):
        partner = _make_partner(pid=50)
        activity_type = MagicMock(id=3)
        activity_type.__bool__ = MagicMock(return_value=True)
        ctx = _patch_schedule_activity_request(
            partner=partner, activity_type=activity_type, created_activity=MagicMock(id=777)
        )
        with ctx:
            result = partner_schedule_activity(_make_user(), {"partner_id": 50, "summary": "Call back"})
        assert result == {"activity_id": 777}

    def test_invalid_partner_raises(self):
        ctx = _patch_schedule_activity_request(partner=None)
        with ctx:
            with pytest.raises(ValueError, match="not found or access denied"):
                partner_schedule_activity(_make_user(), {"partner_id": 999})

    def test_invalid_activity_type_raises(self):
        partner = _make_partner(pid=51)
        ctx = _patch_schedule_activity_request(partner=partner, activity_type=None)
        with ctx:
            with pytest.raises(ValueError, match="Activity type not found"):
                partner_schedule_activity(_make_user(), {"partner_id": 51, "activity_type": "Bogus"})


# ---------------------------------------------------------------------------
# partner_post_message
# ---------------------------------------------------------------------------

def _patch_post_message_request(partner=None):
    mock_request = MagicMock(name="request")
    partner_env = MagicMock()
    if partner is None:
        empty = MagicMock()
        empty.__bool__ = MagicMock(return_value=False)
        partner_env.with_user.return_value.browse.return_value.exists.return_value = empty
    else:
        partner_env.with_user.return_value.browse.return_value.exists.return_value = partner
    mock_request.env.__getitem__.side_effect = (
        lambda model: partner_env if model == "res.partner" else MagicMock()
    )
    ctx = patch.object(partner_actions, "request", mock_request)
    return ctx


class TestPartnerPostMessage:
    def test_message_posted(self):
        partner = _make_partner(pid=60)
        partner.message_post.return_value.id = 900
        ctx = _patch_post_message_request(partner=partner)
        with ctx:
            result = partner_post_message(_make_user(), {"partner_id": 60, "body": "Hello"})
        assert result == {"message_id": 900}

    def test_missing_body_raises(self):
        partner = _make_partner(pid=61)
        ctx = _patch_post_message_request(partner=partner)
        with ctx:
            with pytest.raises(ValueError, match="body is required"):
                partner_post_message(_make_user(), {"partner_id": 61, "body": "  "})

    def test_invalid_partner_raises(self):
        ctx = _patch_post_message_request(partner=None)
        with ctx:
            with pytest.raises(ValueError, match="not found or access denied"):
                partner_post_message(_make_user(), {"partner_id": 999, "body": "Hi"})
