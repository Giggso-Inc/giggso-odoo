# Giggso Odoo MCP

Version: `0.1.0`

Giggso Odoo MCP lets MCP-capable assistants such as Codex, Claude, and other compatible chat tools work with a self-hosted open-source Odoo server. The first version focuses on Odoo CRM and Project, with identity-aware access through Odoo's own users, groups, ACLs, and record rules.

This project is not for Odoo Online. It is designed for a custom install of open-source Odoo where you can install a custom add-on and run a nearby MCP service.

## What It Provides

- MCP tools for CRM leads, opportunities, stages, notes, and project tasks.
- A custom Odoo add-on that receives signed MCP requests.
- An external Python MCP server that chat tools connect to.
- Enterprise OIDC/JWKS identity verification for user identity.
- Odoo-native permission enforcement by mapping the signed identity to `res.users` and executing business access with `with_user(real_user)`.
- No per-user Odoo API keys.
- No direct PostgreSQL access.
- JSONL audit logging in the MCP service and audit events in Odoo.

## Architecture

```text
MCP-capable chat tool
        |
        | Authorization: Bearer <IdP JWT>
        v
Python MCP server
        |
        | Verify RS256 token with JWKS
        | Sign connector request
        v
Odoo MCP Connector add-on
        |
        | Map email/upn/preferred_username -> res.users
        | Execute ORM with with_user(real_user)
        v
Odoo CRM / Project
```

The critical security property is that CRM and Project reads/writes happen as the mapped Odoo user. A shared service account is not used to read business data.

## Repository Layout

```text
odoo_addons/
  odoo_mcp_connector/      Odoo add-on installed on the Odoo server

odoo_mcp_server/
  src/odoo_mcp/            Python MCP server
  tests/                   Unit tests
  Dockerfile               Container image for MCP service

deploy/
  docker-compose.yml       Example deployment for the MCP service
  .env.example             Runtime environment template

docs/
  deployment-runbook.md    Operational deployment checklist
  odoo-mcp-adr-001.md      Architecture decision record
```

## Benefits

- Users can ask a chat tool to work with Odoo without logging into Odoo manually for every task.
- Odoo remains the source of truth for permissions.
- Admins do not need to create or rotate API keys for every Odoo user.
- Offboarding follows existing SSO/Odoo user deactivation paths.
- The MCP surface is narrow and explicit instead of exposing generic model access.
- The system can be deployed beside an existing open-source Odoo server.

## Current Tool Coverage

Admin:

- `odoo_health_check`
- `odoo_list_allowed_capabilities`

CRM:

- `crm_search_opportunities`
- `crm_list_stale_opportunities`
- `crm_list_stages`
- `crm_create_lead`
- `crm_add_note`
- `crm_update_stage`

Project:

- `project_list_projects`
- `project_list_tasks`
- `project_list_task_stages`
- `project_create_task`
- `project_move_task_stage`
- `project_add_comment`

## Install

### 1. Clone the repository

On the Odoo server or on a server in the same private network:

```bash
git clone https://github.com/giggsoinc/giggso-odoo.git
cd giggso-odoo
```

For a guided server install, run:

```bash
bash scripts/install_odoo_mcp.sh
```

### 2. Install the Odoo add-on

Copy the add-on into your Odoo custom addons path:

```bash
cp -R odoo_addons/odoo_mcp_connector /opt/odoo/custom_addons/
```

Make sure your Odoo config includes the custom addons path:

```text
addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons
```

Restart Odoo, update the Apps list, and install **Odoo MCP Connector**.

### 3. Set the connector signing secret

In Odoo developer mode, go to:

```text
Settings -> Technical -> Parameters -> System Parameters
```

Create:

```text
Key:   odoo_mcp_connector.signing_secret
Value: <long-random-secret>
```

The same value must be used as `ODOO_MCP_CONNECTOR_SECRET` in the MCP server.

### 4. Configure Odoo users

Each SSO user must map to an active Odoo user. The connector checks:

```text
res.users.login == identity email
or
res.users.email == identity email
```

Keep user groups, CRM access, Project access, companies, and record rules configured in Odoo.

### 5. Configure the MCP server

For Google Cloud / Google Workspace, use:

```text
ODOO_MCP_IDENTITY_ISSUER=https://accounts.google.com
ODOO_MCP_IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
```

The audience is your Google OAuth Client ID from:

```text
Google Cloud Console -> APIs & Services -> Credentials -> OAuth 2.0 Client IDs
```

Create a private `.env` from `deploy/.env.example`:

```text
ODOO_URL=https://odoo.example.com
ODOO_MCP_CONNECTOR_SECRET=<same-long-random-secret>
ODOO_MCP_IDENTITY_ISSUER=https://idp.example.com
ODOO_MCP_IDENTITY_AUDIENCE=odoo-mcp
ODOO_MCP_IDENTITY_JWKS_URL=https://idp.example.com/.well-known/jwks.json
ODOO_MCP_AUDIT_LOG=/var/log/odoo-mcp/audit.jsonl
ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8088
ODOO_MCP_PUBLIC_URL=https://mcp.example.com
```

Do not commit `.env`.

### 6. Run the MCP service

```bash
cd deploy
docker compose up -d --build
```

The sample Compose file binds the service to `127.0.0.1:8088`. Put it behind HTTPS through Nginx, Caddy, Cloudflare Tunnel, Tailscale, or another controlled access layer.

## Identity Provider Requirements

Your IdP must issue RS256 JWTs and publish a JWKS endpoint. Tokens should include:

```text
sub
email, upn, or preferred_username
iss
aud
exp
```

Common JWKS examples:

```text
Microsoft Entra ID:
https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys

Generic OIDC:
https://idp.example.com/.well-known/jwks.json
```

## Security Model

- The MCP server verifies the user identity token.
- The MCP server signs the internal request to Odoo.
- The Odoo add-on verifies the connector signature.
- Odoo maps the actor email to `res.users`.
- Odoo executes CRM/Project ORM operations with `with_user(real_user)`.
- Odoo ACLs and record rules decide what the user can read or write.

## Development

```bash
cd odoo_mcp_server
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

If you do not install test dependencies, at minimum run:

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
from pathlib import Path
for path in list(Path('src').rglob('*.py')) + list(Path('tests').rglob('*.py')):
    compile(path.read_text(), str(path), 'exec')
print('syntax ok')
PY
```

## Version Notes

`0.1.0` is the first working architecture cut:

- external MCP server
- Odoo connector add-on
- RS256/JWKS identity verification
- CRM and Project tools
- signed service-to-Odoo connector calls
- Odoo-native permission enforcement

The next important features are customer/contact tools, task detail tools, activity tools, richer audit views, and a polished Odoo Marketplace packaging pass.
