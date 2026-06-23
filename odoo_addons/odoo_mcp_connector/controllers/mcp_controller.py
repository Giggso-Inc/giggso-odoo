from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from odoo import http
from odoo.http import request

from .handlers import HANDLERS

_logger = logging.getLogger(__name__)


class OdooMcpController(http.Controller):
    """Signed HTTP entrypoint for MCP calls into Odoo."""

    @http.route("/odoo_mcp/action", type="http", auth="public", methods=["POST"], csrf=False)
    def action(self) -> http.Response:
        """Verify, dispatch, and return one MCP connector action."""
        raw_body = request.httprequest.get_data()
        try:
            self._verify_signature(raw_body)
            result = self._dispatch(json.loads(raw_body.decode("utf-8")))
            return self._json_response({"result": result})
        except Exception as exc:
            _logger.exception("MCP action failed")
            # Roll back the failed action so a partially written record
            # (e.g. a task created before an AccessError on user_ids) is
            # never committed at request end.
            request.env.cr.rollback()
            self._audit(actor_email="unknown", module="unknown", action="error", success=False, detail=str(exc))
            return self._json_response({"error": str(exc)}, status=400)

    def _dispatch(self, payload: dict[str, Any]) -> Any:
        """Map a signed request to a connector action."""
        actor_email = str(payload.get("actor_email") or "")
        module = str(payload.get("module") or "")
        action = str(payload.get("action") or "")
        params = payload.get("params") or {}
        if not actor_email: raise ValueError("actor_email is required")
        if not isinstance(params, dict): raise ValueError("params must be an object")

        handler = HANDLERS.get((module, action))
        if not handler:
            raise ValueError(f"Unsupported MCP action: {module}.{action}")
        user = self._user_for_actor(actor_email)
        # Rebind the request env (and transaction default_env) to the actor.
        # On auth="public" routes the default env is the Public user; Odoo 19
        # resets m2m comodels with _allow_sudo_commands=False (e.g. res.users)
        # to the default env user, so user_ids writes fail without this.
        request.update_env(user=user.id)
        result = handler(user, params)
        self._audit(actor_email=actor_email, module=module, action=action, success=True)
        return result
    def _verify_signature(self, body: bytes) -> None:
        """Verify the connector HMAC signature and timestamp."""
        secret = request.env["ir.config_parameter"].sudo().get_param("odoo_mcp_connector.signing_secret")
        if not secret:
            raise ValueError("Odoo MCP connector signing secret is not configured")
        timestamp = request.httprequest.headers.get("X-Odoo-MCP-Timestamp", "")
        signature = request.httprequest.headers.get("X-Odoo-MCP-Signature", "")
        if not timestamp or not signature:
            raise ValueError("Missing Odoo MCP signature headers")
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise ValueError("Odoo MCP request timestamp is outside the allowed window")
        message = timestamp.encode("utf-8") + b"." + body
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Odoo MCP request signature")

    def _user_for_actor(self, actor_email: str):
        """Resolve an SSO actor email to an active Odoo user."""
        user = request.env["res.users"].sudo().search(
            [("active", "=", True), "|", ("login", "=", actor_email), ("email", "=", actor_email)],
            limit=1,
        )
        if not user:
            raise ValueError(f"No active Odoo user found for MCP actor: {actor_email}")
        return user

    def _audit(self, *, actor_email: str, module: str, action: str, success: bool, detail: str = "") -> None:
        """Write a connector audit event."""
        request.env["odoo.mcp.audit"].sudo().create({
            "actor_email": actor_email, "module": module, "action": action,
            "success": success, "detail": detail,})
    def _json_response(self, payload: dict[str, Any], status: int = 200) -> http.Response:
        """Return a JSON HTTP response."""
        return request.make_response(json.dumps(payload), headers=[("Content-Type", "application/json")], status=status)
