# README — User Manual: Connect & Use

Version: 1.0 · Audience: Giggso internal teams · Last verified: 2026-05-29

This is the **end-user** guide. If you're an operator deploying the
server, see README-DEPLOY.md instead.

---

## What you get

A Claude.ai connector that lets you talk to Giggso's Odoo from chat —
search CRM opportunities, create leads, list and update project
tasks, post notes — all under **your own Odoo identity**.

Every action you take is filtered by Odoo's own permission system:
you can only see and change what your Odoo login already allows.

---

## What you need before connecting

1. A Claude.ai account
2. A Giggso Odoo login (`yourname@giggso.com`) that works at
   `https://odoo.giggso.com`
3. The MCP server URL (we own it): `https://odoo-mcp.giggso.com/`

If you can't log in to Odoo directly, fix that first — the MCP layer
adds nothing your Odoo user can't already do.

---

## Connect Claude.ai to Giggso Odoo

1. Open Claude.ai
2. Settings → **Connectors**
3. Click **Add custom connector** (or "Connect MCP server")
4. Paste the URL exactly:
   ```
   https://odoo-mcp.giggso.com/
   ```
   *(bare base URL, trailing slash, no `/mcp` or `/sse` suffix)*
5. A browser tab opens for OAuth. Sign in with your Giggso Odoo
   credentials.
6. Approve the requested scopes.
7. Back in Claude, the connector should show **Connected** with a
   tool list — `odoo_health_check`, `crm_search_opportunities`,
   `project_list_tasks`, etc.

If something fails partway through, see "Troubleshooting" below.

---

## First-time sanity check

In a new Claude chat, say:

> Run the Odoo health check.

Expected reply (yours will show your own email/uid):
```
status: ok
odoo_user_id: 11
odoo_user_login: ravi@giggso.com
database: gg-odoo-db
```

If you see that, you're fully wired in.

---

## What you can do — top 10 prompts

CRM:
- "Search Giggso CRM opportunities for 'banking' — top 10."
- "Show me CRM opportunities with no next activity."
- "Create a CRM lead: name 'Acme POC', contact 'Jane Doe',
  email 'jane@acme.com'."
- "Add this note to lead 142: 'Demo confirmed for Tuesday 10am.'"
- "Move lead 142 to stage 'Proposal'."

Project Management:
- "List my projects."
- "Show open tasks in project 'Trinity Red Teaming' (id 5)."
- "List task stages for project 5."
- "Create a task in project 5 named 'Draft pen-test report',
  due 2026-06-15."
- "Move task 88 to stage 'UAT Testing'."

See **README-CRM.md** and **README-PROJECT.md** for full tool
references.

---

## Things to know

- **Acts as you.** The MCP server proxies every call under your Odoo
  user. If a teammate asks "can you see lead 200?" — they'll see only
  what their own Odoo permissions allow. There's no shared service
  account.
- **Every action is audited.** Writes (create lead, add note, move
  stage) are logged on the MCP server with `actor`, `model`, and
  `record_id`. Logs do not contain payload values, only field names
  and lengths.
- **Read-then-write is two prompts.** Claude can't speculatively
  write. To "move all stale leads to Won", you'd first list them,
  confirm the ids, then ask Claude to update them.
- **Limits are bounded.** Search tools cap at 50–75 rows per call.
  Ask for ranges if you need more.

---

## Disconnecting

Claude.ai → Settings → Connectors → **Odoo MCP** → Disconnect.

Disconnecting revokes the bearer token. Reconnecting later goes
through OAuth again.

---

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| OAuth tab spins forever | Pop-up blocker | Disable blocker, retry |
| "Authorization with the MCP server failed" | Stale browser session | Sign out of Odoo in that browser, retry |
| Tool list empty after connect | Connector wasn't refreshed | Disconnect + Reconnect |
| `HTTP 404` in a tool error | Cached error from a prior outage | Disconnect + Reconnect |
| `HTTP 400 Missing signature headers` | Server-side misconfig | Ping platform team — not your problem |
| `Odoo connector HTTP 401` | Your Odoo user is disabled | Ask admin to reactivate |
| Tools work but return zero rows | Odoo record-rules limit you | Confirm in Odoo UI you can see the same records |

For anything else, paste the exact error into #giggso-tools and tag
the platform owner.

---

## Privacy & security

- Your Odoo password never reaches Claude. OAuth gives the MCP server
  a session token; the token is exchanged for short-lived bearer
  tokens scoped to your identity.
- The MCP server holds a connector-signing secret (separate from your
  password) that signs each request to Odoo. Odoo refuses any request
  without a valid signature.
- All transport is TLS. Plain-text HTTP returns 404.
- The audit log lives on the MCP server. Ask the platform team if you
  need an export of your own activity.
