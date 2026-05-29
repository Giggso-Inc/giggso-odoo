# README — Debugger Playbook

Version: 1.0 · Last verified: 2026-05-29 · Owner: Giggso platform

Every failure mode we hit getting `Claude.ai ↔ MCP ↔ Odoo addon`
end-to-end live. For each: symptom, root cause, fix, prevention.

> Convention: every command is prefixed **`[MCP SERVER]`**
> (147.224.143.159) or **`[ODOO SERVER]`** (64.181.194.210).

---

## Quick smoke (run before deep-debugging)

**[ODOO SERVER]** — controller alive?
```bash
curl -sS -o /tmp/r.txt -w 'HTTP:%{http_code}\n' \
  -X POST https://odoo.giggso.com/odoo_mcp/action \
  -H 'Content-Type: application/json' -d '{}'
head -c 200 /tmp/r.txt; echo
# expect: HTTP:400 {"error":"Missing Odoo MCP signature headers"}
```

**[MCP SERVER]** — signed round-trip works?
```bash
docker exec deploy-odoo-mcp-1 python -c "
from odoo_mcp.config import load_settings
from odoo_mcp.odoo_client import OdooConnectorClient, OdooConnectorConfig
s = load_settings()
c = OdooConnectorClient(OdooConnectorConfig(url=s.odoo_url,
    secret=s.odoo_connector_secret, timeout_seconds=10))
print(c.call(actor_email='ravi@giggso.com', module='admin',
             action='health', params={}))
"
# expect: {'status': 'ok', 'odoo_user_id': 11, ...}
```

If both return the expected output, the pipeline is healthy and the
problem is client-side (Claude.ai cache, OAuth, tool descriptor).

---

## MCP SERVER failure modes

### M1 — `POST / 404` from Claude

**Symptom:** Claude tries the connector, MCP logs show `POST / 404`.

**Cause:** `ODOO_MCP_TRANSPORT=sse` mounts handlers at `/sse`, not `/`.
Anthropic's marketplace clients post to the bare base URL.

**Fix:** in `.env` set `ODOO_MCP_TRANSPORT=streamable-http`. In
`server.py` the app selects `mcp.streamable_http_app()` and FastMCP
must be constructed with `streamable_http_path="/"` (default is
`/mcp`).

**Prevention:** the `.env.example` ships with `streamable-http`. Never
flip to sse for marketplace builds.

---

### M2 — `POST / 401` after auth succeeds

**Symptom:** OAuth completes, `/token` returns 200, then every tool
call is 401.

**Cause:** `IdentityTokenVerifier` was being built without
`session_secret`, falling back to `secret` from a different env var →
HMAC signature mismatch on the bearer token.

**Fix:** in `app.py`, pass `session_secret=settings.odoo_connector_secret`
explicitly when constructing the verifier.

**Prevention:** type-check the verifier constructor; never accept
defaults for secret material.

---

### M3 — "Authorization with the MCP server failed" popup (no error in logs)

**Symptom:** After `/token` returns 200, Claude.ai shows the popup and
no follow-up requests appear in MCP logs.

**Cause:** Claude.ai is an **OIDC** client; it requires `id_token` in
the `/token` response when `openid` is in granted scopes. Plain OAuth
2 `access_token`-only responses are silently rejected.

**Fix:** in `oauth_token.py`, include `id_token` (signed with the
session secret, `sub` = user login) when `openid` ∈ granted scopes.

**Prevention:** OIDC compliance test in CI.

---

### M4 — `RuntimeError: Task group is not initialized` on every tool call

**Symptom:** `POST / 500` with that exact RuntimeError from
`StreamableHTTPSessionManager`.

**Cause:** FastMCP's streamable-http app has a Starlette lifespan that
**must** wrap our outer Starlette app. The first attempt
(`getattr(mcp_app, "lifespan", None)`) silently returned `None`
because Starlette stores it at `router.lifespan_context`, not as an
app attribute.

**Fix:** in `oauth.py`:
```python
lifespan = mcp_app.router.lifespan_context
outer = Starlette(routes=routes, lifespan=lifespan, ...)
```

**Prevention:** assert `lifespan is not None` at startup.

---

### M5 — Stale env / stale code after `git pull`

**Symptom:** code changes pulled but behaviour unchanged.

**Cause:** `docker compose restart odoo-mcp` reuses the existing
image. The Python package inside the container is whatever was baked
in at build time.

**Fix:** always rebuild:
```bash
[MCP SERVER]$ cd ~/giggso-odoo/deploy
[MCP SERVER]$ docker compose up -d --build --force-recreate odoo-mcp
```

**Prevention:** `--build` is non-negotiable after `git pull`.

---

## ODOO SERVER failure modes

### O1 — Addon marked `uninstallable`

**Symptom:** `odoo.modules.module: The module odoo_mcp_connector has
an incompatible version, setting installable=False`.

**Cause:** Odoo 19 requires a **5-segment** version string. `"1.0"`
and `"19.0.0.1.0"` (4 segments after the leading 19) are both
rejected.

**Fix:** set `"version": "19.0.1.0.0"` (or any
`"19.0.<minor>.<patch>.<build>"`). Compare against existing Odoo 19
addons:
```bash
[ODOO SERVER]$ sudo grep -h '"version"' /opt/helpdesk/*/__manifest__.py
"version": "19.0.1.16.4"
"version": "19.0.1.0.0"
```

**Prevention:** the repo manifest pins `"19.0.1.0.0"` so rsync from
main can't reintroduce the bug.

---

### O2 — `/mnt/extra-addons` shadowed by a second bind-mount

**Symptom:** addon copied to `/home/opc/gg-odoo-app/addons/...` but
`docker compose exec web ls /mnt/extra-addons/odoo_mcp_connector`
returns "No such file or directory".

**Cause:** `docker-compose.yml` has two volumes mounted at the same
path:
```yaml
volumes:
  - ./addons:/mnt/extra-addons       # silently shadowed
  - /opt/helpdesk:/mnt/extra-addons  # wins
```

**Fix (operational):** drop addons into a path that's mounted
without a collision — `/opt/odoo/custom_addons` works.

**Fix (proper, TODO):** merge both source dirs into a single mount, or
remove `./addons` from the compose file. Tracked in cleanup queue.

---

### O3 — `cli/shell.py NameError: name 'os' is not defined`

**Symptom:** odoo shell script errors halfway through.

**Cause:** `odoo shell` does not auto-import `os`. Scripts that read
`os.environ` must include `import os` explicitly at the top of the
heredoc.

**Fix:** start every shell script with:
```python
import os
```

---

### O4 — `Odoo is currently processing another module operation`

**Symptom:** `UserError` on `button_immediate_upgrade()` after a
previous failed upgrade.

**Cause:** Stale `state='to upgrade'` row and/or stuck
`ir.actions.todo` records from the failed attempt.

**Fix:**
```sql
UPDATE ir_module_module SET state='installed'
 WHERE name='odoo_mcp_connector' AND state='to upgrade';
DELETE FROM ir_actions_todo WHERE state='open';
```
Then retry the upgrade.

**Prevention:** never `Ctrl+C` an upgrade. If you must, follow with
the cleanup query above.

---

### O5 — Removed field on `project.task` (`kanban_state`)

**Symptom:** `project_list_tasks` returns `HTTP 400` regardless of
filter.

**Cause:** `kanban_state` was removed from `project.task` in Odoo 17;
our `TASK_FIELDS` constant still listed it. Odoo's `read()` 400s on
unknown fields.

**Fix:** swap `kanban_state` → `state` in two places:
- `odoo_mcp_server/src/odoo_mcp/tools/projects.py`
- `odoo_addons/odoo_mcp_connector/controllers/project_actions.py`

Then rebuild MCP container + upgrade the Odoo module.

**Prevention:** integration test that calls each `project_*` tool
against an Odoo 19 db at CI time.

---

### O6 — Odoo redirects POST → HTTP and serves the website 404 page

**Symptom:** Claude tool call gets back the Odoo "Page Not Found"
HTML; canonical URL in the HTML is `http://...` (not https).

**Cause we ruled out:** misrouted reverse proxy. Not the issue here.

**Actual cause we found:** stale cached error response in Claude.ai's
connector — once the addon was installed and the signed call
succeeded inside the container, **reconnecting the connector** in
Claude flushed the cache.

**Fix:** in Claude → Settings → Connectors → Odoo → Disconnect →
Reconnect. Then retry the tool.

**Prevention:** when tool descriptors or upstream responses change,
disconnect + reconnect, don't expect hot-reload.

---

## How to read MCP audit logs

Every tool call is appended to `/var/log/odoo-mcp/audit.jsonl` inside
the container. To tail in real time:

```bash
[MCP SERVER]$ docker exec deploy-odoo-mcp-1 tail -f /var/log/odoo-mcp/audit.jsonl
```

Fields:
- `actor`: authenticated MCP user email
- `action`: high-level operation (`create`, `write.stage`, `message_post`)
- `model`: Odoo model (`crm.lead`, `project.task`)
- `record_id`: integer id
- `payload`: redacted summary (field names only, no values)

---

## Useful one-liners

```bash
# MCP container — env actually seen by the running process
[MCP SERVER]$ docker exec deploy-odoo-mcp-1 cat /proc/1/environ \
              | tr '\0' '\n' | grep -iE 'odoo|url'

# MCP container — confirm Settings load
[MCP SERVER]$ docker exec deploy-odoo-mcp-1 python -c \
  "from odoo_mcp.config import load_settings as f; \
   s=f(); print(s.odoo_url, s.odoo_db_name, len(s.odoo_connector_secret))"

# Odoo — list addon paths the container actually scans
[ODOO SERVER]$ docker compose logs web --tail 200 | grep 'addons paths'

# Odoo — find a module's manifest version
[ODOO SERVER]$ docker compose exec -T web cat \
  /opt/odoo/custom_addons/odoo_mcp_connector/__manifest__.py
```
