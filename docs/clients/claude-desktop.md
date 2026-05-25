# Claude Desktop ↔ Odoo MCP — connect today

**Version:** Cycle 2 · 2026-05-25
**Goal:** in under 10 minutes, get Claude Desktop on your laptop talking to
the Odoo MCP server on `odoo.giggso.com`, with every tool call running
under your own Odoo identity.
**Scope:** CRM + Project tools only. Recruitment + HR ship in a later cycle.

---

## Pre-reqs

- TLS is terminated by nginx and `https://odoo.giggso.com/mcp/...` works
  without `-k`. See [`nginx-tls.md`](./nginx-tls.md) if not.
- You have an Odoo user that can log in to `https://odoo.giggso.com`.
- Claude Desktop 0.9 or newer (older builds don't support remote MCP).

---

## Step 1 — Issue yourself a long-lived bearer token

Claude Desktop cannot drive the browser-based OAuth flow. The new
`/auth/issue-token` endpoint exchanges your Odoo login for a 90-day JWT
that has the same shape as the cookie-flow session token, so the server's
verifier accepts both with one code path.

Run this from your laptop (replace placeholders):

```bash
curl -sS -X POST https://odoo.giggso.com/mcp/auth/issue-token \
  -H 'Content-Type: application/json' \
  -d '{
        "login":    "you@giggso.com",
        "password": "YOUR_ODOO_PASSWORD",
        "label":    "claude-desktop-laptop"
      }'
```

Expected response:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 7776000,
  "label": "claude-desktop-laptop",
  "subject": "12",
  "email": "you@giggso.com"
}
```

Copy the `token` value. Treat it like a password — it acts as you for 90 days
unless revoked.

**Smoke-test the token before wiring Claude:**

```bash
TOKEN='eyJhbGciOiJIUzI1NiIs...'
curl -sS https://odoo.giggso.com/mcp/auth/whoami \
  -H "Authorization: Bearer $TOKEN"
# expected: {"subject":"12","email":"you@giggso.com","scopes":[]}
```

If `whoami` returns 401, the token is bad — stop and re-issue. Don't
proceed to Claude until `whoami` works.

---

## Step 2 — Wire it into Claude Desktop

Claude Desktop's MCP config lives at:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

There are two transport options. **Try Option A first.** If your Claude
Desktop build does not yet support remote MCP, fall back to Option B.

### Option A — Native remote (streamable HTTP) — preferred

```json
{
  "mcpServers": {
    "giggso-odoo": {
      "transport": {
        "type": "sse",
        "url": "https://odoo.giggso.com/mcp/sse",
        "headers": {
          "Authorization": "Bearer eyJhbGciOiJIUzI1NiIs..."
        }
      }
    }
  }
}
```

### Option B — `mcp-remote` stdio bridge — fallback

If Claude Desktop refuses Option A, use the npm bridge that proxies a remote
SSE server through a local stdio process:

```json
{
  "mcpServers": {
    "giggso-odoo": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://odoo.giggso.com/mcp/sse",
        "--header",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
      ]
    }
  }
}
```

Save the file, then **fully quit and relaunch Claude Desktop**. A reload
inside the app is not enough — the MCP subsystem only re-reads config on
cold start.

---

## Step 3 — Smoke test from inside Claude

In a new Claude chat, ask each of these in order. Stop at the first
failure and check the matching row in the troubleshooting table below.

1. **Identity round-trip**
   > "Call the whoami tool on giggso-odoo and show me the result."
   - Pass criteria: response shows your Odoo email and subject ID.

2. **Read path (no side effects)**
   > "Use giggso-odoo `crm_search_opportunities` to list my top 5 open
   > opportunities by expected revenue."
   - Pass criteria: a non-empty list (or an empty list if you genuinely
     have none), no auth errors.

3. **Write path (creates a real record)**
   > "Use giggso-odoo `crm_create_lead` with name 'Acme MCP Smoke' and
   > expected revenue 50000."
   - Pass criteria: Claude returns a numeric `id`. Open
     `https://odoo.giggso.com` in a browser, go to CRM, find that lead,
     and confirm **the salesperson / owner is you** — not a service
     account. This is the per-user-identity check.

If all three pass, Cycle 2 is done. Delete the smoke lead from the Odoo UI
once you're satisfied.

---

## Troubleshooting

| Symptom                                              | Likely cause                                       | Fix                                                                                       |
| ---------------------------------------------------- | -------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `SSL_ERROR_*` / cert warnings                        | nginx not fronting `:443` with the real cert        | See [`nginx-tls.md`](./nginx-tls.md), Step 2.                                              |
| `401 unauthorized` from `whoami`                     | Token typo or expired                              | Re-issue via `/auth/issue-token`. Tokens are 90 days.                                      |
| `whoami` works in curl but Claude says "no servers"  | Config file in the wrong location, or app not relaunched | Confirm path per OS above. Fully quit Claude Desktop, relaunch.                            |
| `crm_search_opportunities` returns empty             | Your Odoo user has no opportunities, or ACL hides them | Open Odoo web UI and confirm visibility. The MCP enforces your ACLs — same view both places. |
| Lead is created but owner is `__system__`            | Bearer flow attached but `with_user()` not applied   | Server-side bug. Check `odoo_mcp_connector` is the running version with the per-user dispatcher. |
| Tools list shows admin-only tools                    | You logged in as an admin                          | Expected. Other users see only their permitted tools.                                      |

---

## Revoking a token

If a laptop is lost or a token leaks:

```bash
curl -sS -X POST https://odoo.giggso.com/mcp/auth/revoke \
  -H "Authorization: Bearer $TOKEN"
# expected: {"revoked": true, "jti": "..."}
```

**Known limit (Cycle 2):** the revocation denylist is in-memory. If the
MCP service restarts, the denylist clears and the revoked token becomes
valid again until its 90-day `exp`. Cycle 3 moves the denylist into
Postgres. For now, **after revoking, also rotate the Odoo password** if the
threat is credible — that's the only way to be sure a token can never be
reissued by the attacker.

---

## What's not here (Cycle 3 backlog)

- Recruitment and HR tool surfaces — modules exist in Odoo, MCP wrappers not
  yet built.
- `crm_log_activity`, `crm_search_partners`, `crm_convert_lead_to_opportunity`.
- `project_log_timesheet`, `project_close_task`, `project_get_task`,
  `project_list_my_tasks`.
- Postgres-backed OAuth + revocation state.
- Per-token rate limiting (60 req/min).
- Public no-auth `/healthz` for uptime monitors.

If you need any of those today, file an issue on `cycle2/claude-connect`
and we'll prioritise for Cycle 3.
