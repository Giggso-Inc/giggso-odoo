# Odoo MCP Roadmap — Giggso Internal

Scope: Giggso staff only. Not an external product. Not a marketplace listing.

Timelines assume one developer at half-time. Adjust if that changes.

---

## Cycle 2 — OAuth 2.1 + DCR (shipped)

Goal: one-click "Add Custom Connector" in Claude Desktop, zero JSON editing.

Shipped:
- RFC 7591 Dynamic Client Registration (`POST /register`) — Claude Desktop
  self-registers on first connect with no server-side config needed.
- `/authorize` GET now fully parses OAuth params (client_id, redirect_uri,
  code_challenge, state), validates against the DCR store, and stashes a
  flow record.
- `/authorize/odoo` POST now redirects (302) with `?code=&state=` to the
  registered redirect URI instead of returning a success HTML page.
- Discovery metadata (`/.well-known/oauth-authorization-server`) now
  advertises `registration_endpoint`.
- Redirect-URI policy: `localhost:*`, `127.0.0.1:*`, `claude-desktop://`
  all accepted. Remote HTTPS redirect URIs rejected.
- `Client_Install_Scripts/` legacy scripts kept but deprecated in README.

---

## Cycle 3 — Google SSO (2-3 weeks)

Goal: Giggso team members use their Google Workspace login instead of an
Odoo API key. Zero manual token generation.

- Wire existing `/authorize/google` + `/oauth/callback` into the OAuth
  code-grant flow (same pattern as the Odoo path now uses).
- Auto-issue MCP tokens when Google Workspace identity is verified.
- Token TTL tied to the Google session.
- Slack notification for high-impact tool calls (project_create, crm_delete).

---

## Cycle 4 — Token self-service UI (2 weeks)

Goal: teammates mint and revoke their own tokens without bothering Ravi.

- Web UI at `/mcp/auth/token`: HTML form listing active tokens with
  revoke buttons. Login via Odoo session or Google SSO.
- Audit log viewer at `/mcp/admin/audit`: paginated JSONL viewer, gated
  to Odoo admin role.
- Token labels and expiry visible so users can self-diagnose.

---

## Cycle 5 — Group-based permissions (2-3 weeks)

Goal: sales reps can use CRM tools; they cannot run admin or project-delete tools.

- Map Odoo groups to MCP tool allowlists via `ODOO_MCP_TOOL_POLICY_FILE`
  (YAML, checked into repo).
- Policy enforced in `tools/common.py` before each tool call.
- Policy decisions logged to the audit log.

---

## Cycle 6 — Persistent client store (1 week)

Goal: DCR registrations survive server restarts.

- Swap `OAuthClientStore` in-memory dict for a Postgres-backed table.
- Same public interface — no changes to routes or callers.

---

## What is not on this roadmap

- Multi-tenant or white-label deployment
- Odoo.com / Odoo Online support
- External marketplace listing
- Recruitment or HR module tools (deferred until Cycle 7+, if at all)
