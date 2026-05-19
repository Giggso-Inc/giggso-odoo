# Odoo MCP Deployment Runbook

## 1. Prepare Odoo

1. Confirm Odoo version and URL.
2. Confirm CRM and Project apps are installed.
3. Clone the repository:

   ```bash
   git clone https://github.com/giggsoinc/giggso-odoo.git
   cd giggso-odoo
   ```

4. Install the `odoo_mcp_connector` add-on from `odoo_addons/`.
5. Create or identify test users.
6. Confirm each user has only the Odoo groups they should have.
7. Set the Odoo system parameter `odoo_mcp_connector.signing_secret`.

## 2. Prepare Server Files

On the Odoo server or a server in the same private network:

```text
deploy/
├── docker-compose.yml
├── .env
└── audit/
```

Do not commit `.env`.

## 3. Configure Identity

The MCP server no longer stores per-user Odoo API keys. Configure the SSO/OIDC provider to issue short-lived RS256 identity tokens with these claims:

```json
{
  "sub": "idp-user-id",
  "email": "alice@example.com",
  "iss": "https://idp.example.com",
  "aud": "odoo-mcp",
  "exp": 1893456000
}
```

Each MCP client must send the signed identity token:

```text
Authorization: Bearer <signed-identity-token>
```

Configure the MCP server with the IdP issuer, audience, and JWKS URL:

```text
ODOO_MCP_IDENTITY_ISSUER=https://accounts.google.com
ODOO_MCP_IDENTITY_AUDIENCE=<google-oauth-client-id>
ODOO_MCP_IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
```

For Google Cloud / Google Workspace, find the audience value here:

```text
Google Cloud Console -> APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Client ID
```

## 4. Start Service

```bash
cd deploy
docker compose up -d --build
```

The default compose file binds to `127.0.0.1:8088`. Put a reverse proxy or VPN in front of it if remote access is required.

## 5. Validate

Use an MCP-capable client and run:

```text
odoo_health_check
odoo_list_allowed_capabilities
crm_search_opportunities
project_list_projects
```

Then test one controlled write in staging:

```text
project_create_task
crm_add_note
```

## 6. Rollback

```bash
cd deploy
docker compose down
```

If a credential is exposed, rotate the connector signing secret immediately. IdP signing keys rotate through JWKS.
