from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class OdooClientError(RuntimeError):
    """Raised when the Odoo MCP connector rejects or fails a request."""


@dataclass(frozen=True)
class OdooConnectorConfig:
    url: str
    secret: str
    timeout_seconds: int = 30


class OdooConnectorClient:
    """Call the custom Odoo MCP connector module.

    The connector, not this service, is responsible for mapping actor_email to a
    real res.users record and executing business model access with with_user().
    """

    def __init__(self, config: OdooConnectorConfig) -> None:
        self.config = config

    def call(
        self,
        *,
        actor_email: str,
        module: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        payload = {
            "actor_email": actor_email,
            "module": module,
            "action": action,
            "params": params or {},
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = str(int(time.time()))
        request = urllib.request.Request(
            f"{self.config.url}/odoo_mcp/action",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Odoo-MCP-Timestamp": timestamp,
                "X-Odoo-MCP-Signature": sign_body(self.config.secret, timestamp, body),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OdooClientError(f"Odoo connector HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OdooClientError(f"Odoo connector request failed: {exc.reason}") from exc

        data = json.loads(response_body)
        if not isinstance(data, dict):
            raise OdooClientError("Odoo connector returned a non-object response")
        if data.get("error"):
            raise OdooClientError(str(data["error"]))
        return data.get("result")


def sign_body(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
