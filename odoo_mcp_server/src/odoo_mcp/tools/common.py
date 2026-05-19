from __future__ import annotations

from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from ..auth import AuthError


def authenticated_login() -> str:
    token = get_access_token()
    if not token or not token.client_id:
        raise AuthError("Authenticated MCP bearer token is required")
    return token.client_id


def compact_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [compact_record(record) for record in records]


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, tuple | list) and len(value) == 2 and isinstance(value[0], int):
            cleaned[key] = {"id": value[0], "name": value[1]}
        else:
            cleaned[key] = value
    return cleaned


def ilike_domain(field: str, query: str) -> list[Any]:
    return [(field, "ilike", query)] if query else []
