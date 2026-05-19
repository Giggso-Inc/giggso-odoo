from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    odoo_url: str
    odoo_connector_secret: str
    identity_token_secret: str | None
    audit_log: Path
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    public_url: str = "http://127.0.0.1:8000"
    identity_issuer: str | None = None
    identity_audience: str | None = None
    identity_jwks_url: str | None = None


def load_settings() -> Settings:
    odoo_url = require_env("ODOO_URL").rstrip("/")
    return Settings(
        odoo_url=odoo_url,
        odoo_connector_secret=require_env("ODOO_MCP_CONNECTOR_SECRET"),
        identity_token_secret=os.getenv("ODOO_MCP_IDENTITY_TOKEN_SECRET"),
        audit_log=Path(os.getenv("ODOO_MCP_AUDIT_LOG", "/var/log/odoo-mcp/audit.jsonl")),
        transport=os.getenv("ODOO_MCP_TRANSPORT", "stdio"),
        host=os.getenv("ODOO_MCP_HOST", "127.0.0.1"),
        port=parse_port(os.getenv("ODOO_MCP_PORT", "8000")),
        public_url=os.getenv("ODOO_MCP_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
        identity_issuer=os.getenv("ODOO_MCP_IDENTITY_ISSUER"),
        identity_audience=os.getenv("ODOO_MCP_IDENTITY_AUDIENCE"),
        identity_jwks_url=os.getenv("ODOO_MCP_IDENTITY_JWKS_URL"),
    )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid ODOO_MCP_PORT: {value}") from exc
    if port < 1 or port > 65535:
        raise RuntimeError(f"ODOO_MCP_PORT must be between 1 and 65535: {value}")
    return port
