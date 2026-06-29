# ============================================================
# File: utils.py
# Summary: Shared helpers for MCP connector controllers.
#          Normalizes Odoo search_read output so it can be JSON
#          serialized: many2one tuples -> {id,name}; datetime /
#          date -> ISO strings; False kept as-is.
# Version: 19.0.2.0.0
# ============================================================

from __future__ import annotations

from datetime import date, datetime


def compact_records(records: list[dict]) -> list[dict]:
    """Normalize a list of Odoo records for JSON serialization."""
    return [compact_record(record) for record in records]


def compact_record(record: dict) -> dict:
    """Normalize a single Odoo record dict.

    - many2one tuples [id, name] -> {"id": id, "name": name}
    - datetime / date -> ISO 8601 string
    - everything else passed through untouched
    """
    cleaned: dict = {}
    for key, value in record.items():
        cleaned[key] = _normalize_value(value)
    return cleaned


def _normalize_value(value):
    """Recursively coerce a single field value to a JSON-safe form."""
    # many2one comes from search_read as [id, name] (or False)
    if (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], str)
    ):
        return {"id": value[0], "name": value[1]}
    # datas from file-backed ir.attachment returns bytes in Odoo 16+ ORM calls
    if isinstance(value, bytes):
        return value.decode("ascii")  # already base64-encoded
    # datetime first because datetime is a subclass of date
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    # one2many / many2many list of ids — leave alone
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    return value
