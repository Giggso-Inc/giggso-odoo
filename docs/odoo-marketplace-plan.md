# Odoo Marketplace Plan

## Marketplace Positioning

Working title:

```text
AI MCP Connector
```

Purpose:

Allow Odoo administrators to safely connect CRM and Projects to an external MCP server for AI-assisted workflows.

## Marketplace Package

The marketplace package is an Odoo addon:

```text
odoo_mcp_connector/
├── __init__.py
├── __manifest__.py
├── controllers/
│   └── main.py
├── models/
│   ├── mcp_settings.py
│   └── mcp_audit_log.py
├── security/
│   ├── security.xml
│   └── ir.model.access.csv
├── views/
│   ├── mcp_settings_views.xml
│   └── mcp_audit_log_views.xml
├── static/description/
│   ├── icon.png
│   └── index.html
└── doc/
    └── index.rst
```

## Addon Responsibilities

- Admin settings page.
- User group for MCP access.
- Connector enable/disable switch.
- CRM/Project feature toggles.
- Audit log model and views.
- Optional health/capabilities endpoint.
- Clear documentation that an external MCP server is required.

## Manifest Fields

The `__manifest__.py` should include:

- `name`
- `summary`
- `version`
- `category`
- `depends`
- `license`
- `author`
- `website`
- `support`
- `images`
- `price` and `currency`, if paid

## Marketplace Disclosure

The listing must clearly state:

- The addon connects Odoo to an external MCP server.
- CRM and Projects are the first supported apps.
- Per-user Odoo permissions are respected.
- No HR/accounting access is enabled by default.
- Customer controls deployment and credentials unless using a hosted plan.
- What data leaves Odoo, when, and why.

## Submission Steps

1. Build and test addon on the target Odoo version.
2. Add icon and screenshots.
3. Write `static/description/index.html`.
4. Write `doc/index.rst`.
5. Confirm license and pricing.
6. Place the addon in a Git repository.
7. Give Odoo Apps access to the repository.
8. Submit through Odoo Apps.
9. Validate the published listing.
