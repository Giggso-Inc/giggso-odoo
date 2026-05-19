# ADR-001: Deploy Odoo MCP as External Docker Service with Odoo Connector Addon

## Status

Proposed

## Context

The company uses open source Odoo, primarily CRM and Projects. Users need a simple way to interact with Odoo from Claude and later from Microsoft Teams, Google Chat, or other clients.

The integration needs per-user authorization, Odoo-native permission enforcement, and a path to publish an Odoo Marketplace app.

## Decision

Build the core MCP runtime as an external Docker service. Build a separate Odoo addon for connector configuration, access visibility, audit logs, and marketplace distribution.

## Rationale

- MCP is a server protocol and fits naturally as an external service.
- Odoo should remain the business system and permission source of truth.
- Teams and Google Chat require bot/webhook services that should not run inside Odoo workers.
- Marketplace distribution works best as a normal installable Odoo module.
- Docker deployment keeps the production runtime portable and supportable.

## Consequences

### Positive

- Clean separation of concerns.
- Easier deployment and rollback.
- Marketplace-friendly Odoo addon.
- Supports Claude first and chat integrations later.
- Avoids direct PostgreSQL access.

### Negative

- Customers must deploy or subscribe to an external MCP service.
- Per-user auth requires secure token onboarding.
- More moving parts than a pure Odoo addon.

## Rejected Alternatives

### Put the full MCP server inside Odoo

Rejected because Odoo workers are not ideal for MCP sessions, external bot integrations, or long-running AI tool workflows.

### Use one service account for all writes

Rejected for production because users need to update Odoo as themselves. A service account may be acceptable for a read-only prototype.

### Connect directly to PostgreSQL

Rejected because it bypasses Odoo ACLs, record rules, business logic, chatter, automation, and audit expectations.
