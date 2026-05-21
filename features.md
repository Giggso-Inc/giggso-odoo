# Features

This file lists the product surface in plain terms.

## Identity and access

- Browser-based login for plain Odoo username/password environments.
- Browser-based Google sign-in when Google SSO is configured.
- RS256/JWKS identity verification for external IdP tokens.
- Short-lived session handling for MCP access.
- Odoo-side identity mapping to `res.users`.
- Odoo-native ACL and record-rule enforcement.

## Connector architecture

- External MCP service runs beside the Odoo instance.
- Odoo connector add-on receives signed requests from the MCP service.
- No direct PostgreSQL access.
- No per-user Odoo API key management.
- No shared service account reads of business data.

## CRM features

- Search leads and opportunities.
- List stale opportunities.
- List CRM stages.
- Create leads.
- Add chatter notes.
- Move opportunities between stages.

## Project features

- List projects.
- List tasks.
- List task stages.
- Create tasks.
- Move tasks between stages.
- Add task comments.

## Admin features

- Health check endpoint.
- Capability listing.
- JSONL audit log on the MCP service.
- Odoo audit trail through chatter and ORM actions.

## Deployment features

- Docker Compose example for the MCP service.
- Guided installer script.
- TLS support using existing server certificates when available.
- Direct HTTPS hosting for the MCP endpoint.
- Hostname-based public URLs.

## Operator controls

- `ODOO_URL`
- `ODOO_DB_NAME`
- `ODOO_MCP_CONNECTOR_SECRET`
- `ODOO_MCP_IDENTITY_ISSUER`
- `ODOO_MCP_IDENTITY_AUDIENCE`
- `ODOO_MCP_IDENTITY_JWKS_URL`
- `ODOO_MCP_PUBLIC_URL`
- `ODOO_MCP_GOOGLE_CLIENT_ID` optional

## Current limitations

- No customer/contact-specific tool set yet.
- No dedicated activity management tool set yet.
- No rich task detail tool yet.
- Google sign-in is optional and must be configured explicitly.
- Odoo Online is not supported.

## Near-term roadmap

- Customer and contact lookup tools.
- Task detail and attachment views.
- Activity scheduling and completion tools.
- Better audit dashboards.
- Marketplace packaging after the self-hosted flow is stable.
