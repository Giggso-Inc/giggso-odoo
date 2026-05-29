# README — Deploy (End-to-End)

Version: 1.0 · Last verified: 2026-05-29 · Owner: Giggso platform

This doc walks every step from a clean state to a working
`Claude.ai ↔ MCP server ↔ Odoo addon ↔ Postgres` pipeline. It is the
exact sequence we ran in production.

> Marketplace shape: the MCP server speaks **streamable-http at the
> URL root**. Marketplace clients configure with a bare base URL.

---

## 0. Topology

| Role | Host | Public URL | Notes |
| --- | --- | --- | --- |
| Odoo runtime (old VM) | `64.181.194.210` | `https://odoo.giggso.com` | docker-compose `web` = `odoo:19.0`, `db` = `postgres:15` |
| MCP server (new VM) | `147.224.143.159` | `https://odoo-mcp.giggso.com` | docker-compose `odoo-mcp` |
| Database | inside old VM `db` container | n/a | `gg-odoo-db`, user `odoo` |

SSH key: `~/.ssh/odoo-mcp-server.pem` (works for both VMs).

---

## 1. Prerequisites

- Docker + docker compose v2 installed on both VMs
- DNS A-records pointing both subdomains at the right VM
- TLS terminated at nginx in front of each VM (handled outside this repo)
- Outbound HTTPS allowed from MCP VM → Odoo VM (443)
- A shared secret generator: `openssl rand -hex 32`

---

## 2. Generate the shared connector secret

The same secret lives in two places:
- MCP server `.env` → `ODOO_MCP_CONNECTOR_SECRET`
- Odoo `ir.config_parameter` → `odoo_mcp_connector.signing_secret`

```bash
openssl rand -hex 32
```

Save it once. Never echo it again.

---

## 3. Old VM — install the Odoo addon

### 3a. Take a Postgres backup first

```bash
cd /home/opc/gg-odoo-app
mkdir -p ~/backup
docker compose exec -T db pg_dump -U odoo -d gg-odoo-db | gzip \
  > ~/backup/gg-odoo-db-$(date +%Y%m%d-%H%M).sql.gz
ls -lh ~/backup/
```

### 3b. Drop the addon onto an addons path Odoo actually scans

`docker-compose.yml` in this repo mounts `/opt/odoo/custom_addons` into the
container. Put the module **there** — the `./addons` mount was historically
shadowed by `/opt/helpdesk` (see DEBUG doc, "duplicate mount" landmine).

```bash
sudo rsync -a /home/opc/giggso-odoo/odoo_addons/odoo_mcp_connector/ \
              /opt/odoo/custom_addons/odoo_mcp_connector/
sudo ls -la /opt/odoo/custom_addons/odoo_mcp_connector/
```

### 3c. Verify the manifest version

Odoo 19 requires a **5-segment** version string. We learned this the hard
way — `"1.0"` and `"19.0.0.1.0"` both fail with
`incompatible version, setting installable=False`.

Working format: `"19.0.<minor>.<patch>.<build>"` — e.g. `"19.0.1.0.0"`.

```bash
sudo grep version /opt/odoo/custom_addons/odoo_mcp_connector/__manifest__.py
# must print:   "version": "19.0.1.0.0",
```

### 3d. Restart Odoo so the registry re-reads the manifest

```bash
cd /home/opc/gg-odoo-app
docker compose restart web
sleep 8
docker compose logs web --tail 50 | grep -iE 'odoo_mcp|incompatible|modules loaded'
# expected: "181 modules loaded ... Modules loaded."
# expected: NO "incompatible version" line
```

### 3e. Install the addon + write the signing secret

```bash
cd /home/opc/gg-odoo-app
set -a; source .env; set +a
read -rsp 'secret: ' MCPSECRET; echo
docker compose exec -e MCPSECRET="$MCPSECRET" -T web odoo shell \
  --no-http -d gg-odoo-db \
  --db_host=db --db_port=5432 --db_user=odoo --db_password="$DB_PASSWORD" <<'PY'
import os
m = env['ir.module.module'].sudo()
m.update_list()
mod = m.search([('name','=','odoo_mcp_connector')], limit=1)
print('BEFORE:', mod.name, mod.state)
if mod.state == 'uninstalled':
    mod.button_immediate_install()
    env.cr.commit()
mod = m.search([('name','=','odoo_mcp_connector')], limit=1)
print('AFTER state:', mod.state)
env['ir.config_parameter'].sudo().set_param(
    'odoo_mcp_connector.signing_secret',
    os.environ['MCPSECRET'],
)
print('secret len:', len(env['ir.config_parameter'].sudo().get_param(
    'odoo_mcp_connector.signing_secret') or ''))
PY
```

Expected:
```
BEFORE: odoo_mcp_connector uninstalled
AFTER state: installed
secret len: 64
```

### 3f. Smoke-test the controller (from the old VM itself)

```bash
curl -sS -o /tmp/r.txt -w 'HTTP:%{http_code}\n' \
  -X POST https://odoo.giggso.com/odoo_mcp/action \
  -H 'Content-Type: application/json' -d '{}'
head -c 300 /tmp/r.txt; echo
```

Expected: `HTTP:400  {"error": "Missing Odoo MCP signature headers"}`.
**400 means success** — the controller is live and refusing unsigned
input. Only 404 is bad.

---

## 4. New VM — MCP server

### 4a. `.env` (the four knobs that matter)

```ini
ODOO_URL=https://odoo.giggso.com
ODOO_DB_NAME=gg-odoo-db
ODOO_MCP_CONNECTOR_SECRET=<paste 64-char secret from step 2>
ODOO_MCP_PUBLIC_URL=https://odoo-mcp.giggso.com
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8443
ODOO_MCP_TRANSPORT=streamable-http
```

`ODOO_MCP_TRANSPORT=streamable-http` is **mandatory** for marketplace
clients. `sse` mounts at `/sse` and breaks bare-base-URL clients.

### 4b. Build and run

```bash
cd ~/giggso-odoo
git pull
cd deploy
docker compose up -d --build --force-recreate odoo-mcp
sleep 5
docker logs deploy-odoo-mcp-1 --tail 15
```

`--build` is required when `git pull` brought new code. `--force-recreate`
alone reuses the cached image.

### 4c. Smoke-test from inside the MCP container

```bash
docker exec deploy-odoo-mcp-1 python -c "
from odoo_mcp.config import load_settings
from odoo_mcp.odoo_client import OdooConnectorClient, OdooConnectorConfig
s = load_settings()
cfg = OdooConnectorConfig(url=s.odoo_url, secret=s.odoo_connector_secret,
                          timeout_seconds=10)
c = OdooConnectorClient(cfg)
print(c.call(actor_email='ravi@giggso.com', module='admin',
             action='health', params={}))
"
```

Expected:
```
{'status': 'ok', 'odoo_user_id': 11,
 'odoo_user_login': 'ravi@giggso.com', 'database': 'gg-odoo-db'}
```

If this returns OK, the pipeline is live. The Claude.ai connector will
work.

---

## 5. Connect Claude.ai

See **README-USER.md** for the end-user steps. In short:
1. Settings → Connectors → Add custom MCP
2. URL: `https://odoo-mcp.giggso.com/` (bare base URL, no path suffix)
3. OAuth: walk through the DCR flow Claude pops up
4. Tool list should populate with `odoo_health_check`,
   `odoo_list_allowed_capabilities`, plus CRM and Project tools

---

## 6. Rollback

If anything breaks:
- **Addon broke Odoo**: `docker compose exec web odoo shell ... ;
  mod.button_immediate_uninstall(); env.cr.commit()`
- **Worst case**: `gunzip -c ~/backup/gg-odoo-db-YYYYMMDD-HHMM.sql.gz |
  docker compose exec -T db psql -U odoo gg-odoo-db`
- **MCP broke**: `cd ~/giggso-odoo && git revert <bad-commit> && cd
  deploy && docker compose up -d --build odoo-mcp`

---

## 7. What success looks like

- `docker compose logs web` shows the addon loaded, no "incompatible"
- Old VM curl to `/odoo_mcp/action` returns **400 missing signature**
- MCP container python smoke returns `status: ok`
- Claude.ai tool call `odoo_health_check` returns the same JSON
