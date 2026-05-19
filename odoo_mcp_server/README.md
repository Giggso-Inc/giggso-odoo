# Odoo MCP Server

Secure MCP server for open source Odoo CRM and Projects.

## Scope

This server exposes a controlled set of MCP tools for:

- CRM opportunities and leads.
- Project tasks and Kanban stages.
- Chatter comments.
- Activities.
- Health and capability checks.

It does not connect directly to PostgreSQL. All operations go through the custom Odoo MCP connector add-on, which maps the signed identity to an Odoo user and uses Odoo ORM with `with_user(real_user)` so ACLs and record rules remain the source of truth.

## Development Run

```bash
cd odoo_mcp_server
python -m venv .venv
. .venv/bin/activate
pip install -e .
odoo-mcp-server
```

## Environment

Copy `.env.example` to a private `.env` file on the server. Do not commit `.env`.

```text
ODOO_URL=https://odoo.example.com
ODOO_MCP_CONNECTOR_SECRET=replace-with-shared-connector-signing-secret
ODOO_MCP_IDENTITY_ISSUER=https://idp.example.com
ODOO_MCP_IDENTITY_AUDIENCE=odoo-mcp
ODOO_MCP_IDENTITY_JWKS_URL=https://idp.example.com/.well-known/jwks.json
ODOO_MCP_AUDIT_LOG=/var/log/odoo-mcp/audit.jsonl
ODOO_MCP_TRANSPORT=stdio
```

Install the `odoo_mcp_connector` add-on in Odoo, then set this Odoo system parameter to the same value as `ODOO_MCP_CONNECTOR_SECRET`:

```text
odoo_mcp_connector.signing_secret
```

## Tool Identity

Every HTTP MCP call must include:

```text
Authorization: Bearer <signed-identity-token>
```

The server verifies the IdP-issued RS256 identity token with JWKS and forwards the actor email to the Odoo connector. The connector maps that email to an active Odoo user and performs CRM/Project operations with that user's Odoo permissions.

## Production Notes

- Run behind a private network or authenticated gateway.
- Issue short-lived identity tokens from your SSO gateway.
- Keep `ODOO_MCP_CONNECTOR_SECRET` private.
- Do not expose this service publicly without authentication.
- Keep destructive tools disabled unless a formal approval flow exists.
