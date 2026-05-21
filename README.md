# Giggso Odoo MCP

Version: `0.1.0`

Giggso Odoo MCP connects MCP-capable assistants such as Claude, Codex, and compatible chat clients to a self-hosted, open-source Odoo instance. It is designed for organizations that want to keep Odoo as the source of truth for access control while letting users ask natural-language questions about CRM and Projects.

This project is **not** for Odoo Online. It is built for a custom Odoo deployment where you can install an add-on and run a nearby MCP service.

## What this is for

- Ask a chat assistant to search CRM leads, create opportunities, add notes, or move stages.
- Ask a chat assistant to list projects, inspect tasks, add comments, or move task stages.
- Keep Odoo permissions in Odoo instead of duplicating them in the MCP layer.
- Avoid per-user Odoo API key management.
- Support either plain Odoo login or Google-based SSO, depending on the environment.

## What it is not

- Not a replacement for Odoo.
- Not for Odoo Online.
- Not a raw SQL integration.
- Not a shared-service-account system that bypasses Odoo permissions.

## Architecture

```text
MCP client
    |
    | Browser login or bearer token
    v
Odoo MCP service
    |
    | Verify identity token or short-lived session
    | Sign internal connector request
    v
Odoo MCP Connector add-on
    |
    | Map identity -> res.users
    | Execute ORM with with_user(real_user)
    v
Odoo CRM / Project
```

The important security property is that Odoo itself decides what the user can see or change.

## Main capabilities

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

## Benefits

- Users can work with Odoo from a chat tool instead of jumping back and forth between screens.
- Odoo remains the permission boundary.
- The platform supports both browser-based login and direct Odoo login.
- Admins do not need to create and rotate a separate Odoo API key for every user.
- The integration runs beside an existing open-source Odoo deployment.
- The MCP surface is narrow, explicit, and auditable.

## Repository layout

```text
odoo_addons/
  odoo_mcp_connector/      Odoo add-on installed on the Odoo server

odoo_mcp_server/
  src/odoo_mcp/            External MCP service
  tests/                   Unit tests
  Dockerfile               Container image for the MCP service

deploy/
  docker-compose.yml       Example deployment
  .env.example             Runtime environment template

docs/
  deployment-runbook.md    Operational checklist
  odoo-mcp-adr-001.md      Architecture decision record
```

## Install

### 1. Clone the repository

```bash
git clone https://github.com/giggsoinc/giggso-odoo.git
cd giggso-odoo
```

### 2. Run the installer

```bash
bash scripts/install_odoo_mcp.sh
```

The installer:

- writes `deploy/.env`
- copies the Odoo connector add-on
- reuses existing TLS certs when available
- starts the MCP service with Docker Compose when Docker is available

### 3. Install the Odoo add-on

Copy the add-on into your Odoo custom addons path:

```bash
cp -R odoo_addons/odoo_mcp_connector /opt/odoo/custom_addons/
```

Make sure the Odoo config includes the custom addons path:

```text
addons_path = /opt/odoo/odoo/addons,/opt/odoo/custom_addons
```

Restart Odoo, update Apps, and install **Odoo MCP Connector**.

### 4. Configure the connector secret

In Odoo developer mode:

```text
Settings -> Technical -> Parameters -> System Parameters
```

Create:

```text
Key:   odoo_mcp_connector.signing_secret
Value: <long-random-secret>
```

Use the same value in:

```text
ODOO_MCP_CONNECTOR_SECRET=<same-long-random-secret>
```

### 5. Configure login mode

The server supports two login modes:

- **Plain Odoo login** when you only have Odoo usernames and passwords.
- **Google SSO** when you set `ODOO_MCP_GOOGLE_CLIENT_ID` and the Google OAuth redirect URI.

### 6. Configure the MCP service

Create `deploy/.env` from `deploy/.env.example` and fill in the actual values.

Common values:

```text
ODOO_URL=https://odoo.example.com
ODOO_DB_NAME=odoo-prod
ODOO_MCP_CONNECTOR_SECRET=<same-long-random-secret>
ODOO_MCP_IDENTITY_ISSUER=https://accounts.google.com
ODOO_MCP_IDENTITY_AUDIENCE=<google-oauth-client-id-or-org-audience>
ODOO_MCP_IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
ODOO_MCP_PUBLIC_URL=https://odoo.example.com:8443
ODOO_MCP_TRANSPORT=sse
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8443
ODOO_MCP_BIND=0.0.0.0
ODOO_MCP_TLS_CERT_FILE=/run/odoo-mcp/certs/tls.crt
ODOO_MCP_TLS_KEY_FILE=/run/odoo-mcp/certs/tls.key
```

### 7. Start the service

```bash
cd deploy
docker compose up -d --build
```

## Google SSO configuration

If you want Google sign-in:

1. Create or reuse a Google OAuth client in Google Cloud Console.
2. Register this redirect URI:
   ```text
   <ODOO_MCP_PUBLIC_URL>/oauth/callback
   ```
3. Set:
   ```text
   ODOO_MCP_GOOGLE_CLIENT_ID=<google-oauth-client-id>
   ```

If this variable is unset, the landing page shows only the Odoo login path.

## Identity provider requirements

The identity provider must publish a JWKS endpoint and issue RS256 JWTs with claims such as:

- `sub`
- `email`, `upn`, or `preferred_username`
- `iss`
- `aud`
- `exp`

Examples:

```text
Microsoft Entra ID:
https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys

Google Workspace:
https://www.googleapis.com/oauth2/v3/certs
```

## Client connection

Point your MCP-capable client at:

```text
https://odoo.example.com:8443/sse
```

If the client supports browser authorization, it should use the `/authorize` flow. If it does not, you can still use the plain Odoo login path from the landing page.

## Example prompts

CRM:

```text
Search CRM opportunities for ACME.
```

```text
Create a lead for Jane Smith at jane@acme.example.
```

```text
Add a note to lead 123: customer wants pricing by Friday.
```

Project:

```text
List my projects.
```

```text
Show tasks in project 42.
```

```text
Move task 987 to stage 12.
```

## Security model

- The MCP service verifies identity.
- The MCP service signs the connector request.
- The Odoo connector verifies that signature.
- The Odoo connector maps the actor identity to `res.users`.
- Odoo executes business access with `with_user(real_user)`.
- Odoo ACLs and record rules remain the source of truth.

## Troubleshooting

- If the landing page still shows an IP instead of a hostname, check `ODOO_MCP_PUBLIC_URL` in `deploy/.env`.
- If Google still appears unexpectedly, check `ODOO_MCP_GOOGLE_CLIENT_ID`.
- If the connector does not appear in Odoo Apps, confirm the add-on is in the mounted custom addons path.
- If the MCP service is unreachable, verify Docker port mapping and cloud firewall rules.

## Development

```bash
cd odoo_mcp_server
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

If you do not install test dependencies, at minimum run a syntax check:

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
from pathlib import Path
for path in list(Path('src').rglob('*.py')) + list(Path('tests').rglob('*.py')):
    compile(path.read_text(), str(path), 'exec')
print('syntax ok')
PY
```

## Related docs

- [how-to.md](how-to.md)
- [features.md](features.md)
- [docs/deployment-runbook.md](docs/deployment-runbook.md)
