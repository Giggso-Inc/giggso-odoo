from __future__ import annotations


def compact_records(records: list[dict]) -> list[dict]:
    """Convert Odoo relation pairs in a list of records."""
    return [compact_record(record) for record in records]


def compact_record(record: dict) -> dict:
    """Convert Odoo many2one values from [id, name] to objects."""
    cleaned = {}
    for key, value in record.items():
        if isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[0], int):
            cleaned[key] = {"id": value[0], "name": value[1]}
        else:
            cleaned[key] = value
    return cleaned
