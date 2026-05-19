from __future__ import annotations

from odoo_mcp.tools.common import compact_record


def test_compact_record_converts_odoo_many2one_pair():
    assert compact_record({"partner_id": [7, "ACME"]}) == {"partner_id": {"id": 7, "name": "ACME"}}


def test_compact_record_leaves_plain_values():
    assert compact_record({"name": "Deal"}) == {"name": "Deal"}
