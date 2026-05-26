# Odoo MCP Roadmap — Giggso Internal

Scope: Giggso staff only. Not an external product. Not a marketplace listing.

Timelines assume one developer at half-time. Adjust if that changes.

---

## Cycle 3 — Token self-service (2 weeks)

Goal: teammates mint and revoke their own tokens without bothering Ravi.

- Web UI at `/mcp/auth/token`: HTML form listing the user's active tokens with
  revoke buttons. Login via Odoo session or Google Workspace SSO
  (google_oauth_client_id wiring already exists).
- Audit log viewer at `/mcp/admin/audit`: paginated JSONL viewer, gated to Odoo
  admin role. No separate auth stack needed — reuse the bearer verifier.
- Token labels and expiry visible in the UI so users can self-diagnose "my token
  expired" without reading raw logs.

---

## Cycle 4 — Group-based permissions (2-3 weeks)

Goal: sales reps can use CRM tools; they cannot run admin or project-delete tools.

- Map Odoo groups to MCP tool allowlists via a new env var
  `ODOO_MCP_TOOL_POLICY_FILE` pointing to a YAML file checked into the repo.
- Policy enforced in `tools/common.py` before each tool call — hard reject, not
  just a soft warning.
- Policy decisions logged to the existing audit log with the group and tool name.

---

## Cycle 5 — Google Workspace identity integration (3-4 weeks)

Goal: zero-touch token issuance; a Giggso employee's Google login is the credential.

- Auto-issue tokens when a Google Workspace identity is verified at login — no
  manual `curl /auth/issue-token` needed.
- Token TTL tied to the Workspace session (revoked when the session ends or the
  user is offboarded in the Workspace admin console).
- Slack notification when a high-impact tool runs (e.g., `project_create`,
  `crm_delete`) so the team has ambient awareness of what the assistant is doing.

---

## What is not on this roadmap

- Multi-tenant or white-label deployment
- Odoo.com / Odoo Online support
- External marketplace listing
- Recruitment or HR module tools (deferred until Cycle 6+, if at all)
