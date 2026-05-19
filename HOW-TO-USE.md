# How To Use Giggso Odoo MCP

This guide explains how an operator configures the system and how a user works with Odoo from an MCP-capable chat tool.

## Operator Setup

1. Clone the repository:

```bash
git clone https://github.com/giggsoinc/giggso-odoo.git
cd giggso-odoo
```

2. Run the guided installer:

```bash
bash scripts/install_odoo_mcp.sh
```

The installer copies the add-on, writes `deploy/.env`, restarts Odoo when possible, and starts the Docker Compose MCP service when Docker is available.

For Google Cloud / Google Workspace, choose option `1` when the installer asks for the identity provider. The installer fills:

```text
OIDC issuer URL: https://accounts.google.com
OIDC JWKS URL:   https://www.googleapis.com/oauth2/v3/certs
```

When it asks for `OIDC audience / OAuth Client ID`, use the Google OAuth client ID from:

```text
Google Cloud Console
-> APIs & Services
-> Credentials
-> OAuth 2.0 Client IDs
-> Client ID
```

If you do not have an OAuth client yet, create one in Google Cloud Console:

```text
APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
```

Use that generated **Client ID** as:

```text
ODOO_MCP_IDENTITY_AUDIENCE=<google-oauth-client-id>
```

Manual install path:

1. Install the Odoo add-on:

```bash
cp -R odoo_addons/odoo_mcp_connector /opt/odoo/custom_addons/
```

2. Restart Odoo and install **Odoo MCP Connector** from Apps.

3. Create a long random connector secret and set it in Odoo:

```text
Settings -> Technical -> Parameters -> System Parameters

odoo_mcp_connector.signing_secret = <long-random-secret>
```

4. Configure the MCP server `.env` with the same connector secret:

```text
ODOO_URL=https://odoo.example.com
ODOO_MCP_CONNECTOR_SECRET=<long-random-secret>
ODOO_MCP_IDENTITY_ISSUER=https://accounts.google.com
ODOO_MCP_IDENTITY_AUDIENCE=<google-oauth-client-id>
ODOO_MCP_IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8088
ODOO_MCP_PUBLIC_URL=https://mcp.example.com
```

5. Start the MCP service:

```bash
cd deploy
docker compose up -d --build
```

6. Put the service behind HTTPS. Do not expose plain HTTP directly to the internet.

7. Confirm Odoo user identity mapping. The IdP token must contain an email-like claim that matches either:

```text
res.users.login
res.users.email
```

8. Validate with a low-risk user first:

```text
odoo_health_check
odoo_list_allowed_capabilities
project_list_projects
crm_search_opportunities
```

## MCP Client Setup

Configure your MCP-capable client to connect to the deployed MCP server URL, for example:

```text
https://mcp.example.com
```

The client or gateway must attach a valid IdP-issued token:

```text
Authorization: Bearer <idp-issued-jwt>
```

The token is verified by the MCP server using:

```text
ODOO_MCP_IDENTITY_ISSUER
ODOO_MCP_IDENTITY_AUDIENCE
ODOO_MCP_IDENTITY_JWKS_URL
```

For Google Cloud / Google Workspace:

```text
ODOO_MCP_IDENTITY_ISSUER=https://accounts.google.com
ODOO_MCP_IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
ODOO_MCP_IDENTITY_AUDIENCE=<OAuth Client ID from Google Cloud Console>
```

## Example User Prompts

Health and access:

```text
Check whether I can access Odoo.
```

```text
List my available Odoo capabilities.
```

CRM:

```text
Search Odoo CRM opportunities for ACME.
```

```text
Create a CRM lead named "ACME expansion" with contact Jane Smith and email jane@acme.example.
```

```text
Show stale opportunities that have no planned next activity.
```

```text
Add a note to lead 123: Customer asked for pricing by Friday.
```

Project:

```text
List my Odoo projects.
```

```text
List tasks in project 42.
```

```text
Create a task in project 42 called "Prepare onboarding checklist" due 2026-06-01.
```

```text
Move task 987 to stage 12.
```

```text
Add a comment to task 987: Waiting on customer confirmation.
```

## Permission Behavior

The assistant cannot see or change records just because MCP is connected. The flow is:

```text
signed user identity -> Odoo user -> Odoo ACLs and record rules
```

If the user cannot see a lead, project, or task in Odoo, the MCP connector should not return it.

## Smoke Test Checklist

Run these checks in staging before production:

- User A can list only the projects they can see in Odoo.
- User B with less access cannot see User A's restricted records.
- A CRM write creates an Odoo chatter/audit trail.
- A task write respects project permissions.
- Invalid JWTs are rejected.
- Expired JWTs are rejected.
- Requests with the wrong connector secret are rejected by Odoo.

## Troubleshooting

`No active Odoo user found for MCP actor`

The IdP email/upn/preferred_username claim does not match an active Odoo user login or email.

`Odoo MCP connector signing secret is not configured`

Set `odoo_mcp_connector.signing_secret` in Odoo system parameters.

`Invalid Odoo MCP request signature`

`ODOO_MCP_CONNECTOR_SECRET` in the MCP server does not match the Odoo system parameter.

`OIDC identity token rejected`

Check issuer, audience, token expiry, and JWKS URL.

`Tool returns no records`

Check the mapped Odoo user's CRM/Project access, company access, and record rules.

## Operational Rules

- Do not create per-user Odoo API keys for MCP.
- Do not expose generic Odoo XML-RPC to chat clients.
- Do not connect MCP directly to PostgreSQL.
- Do not commit `.env`, connector secrets, IdP secrets, or generated key files.
- Rotate `ODOO_MCP_CONNECTOR_SECRET` if it is exposed.
