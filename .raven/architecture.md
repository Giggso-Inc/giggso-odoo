# Odoo MCP Server Architecture

## Overview
Secure Model Context Protocol (MCP) server for Odoo CRM and Projects. Implements RFC 7591 DCR (Dynamic Client Registration) and OAuth 2.0 authorization-code flow for seamless integration with Claude Desktop.

## Components

### Core Services
- **MCP Server**: Starlette/Uvicorn-based MCP endpoint
- **OAuth Handler**: RFC 7591 DCR + authorization code flow
- **CRM/Projects Gateway**: Secure proxy to Odoo models
- **Security Layer**: JWT validation, multi-company rules

### Architecture
```
Claude Desktop
    ↓
MCP Protocol (HTTP/WebSocket)
    ↓
Odoo MCP Server
    ├─ OAuth/DCR Handler (JWT validation)
    ├─ CRM Gateway (res.partner, crm.lead, crm.opportunity)
    ├─ Projects Gateway (project.project, project.task)
    └─ Security Filter (ir.rule, company isolation)
    ↓
Odoo Database (PostgreSQL)
    ├─ res.company (multi-company isolation)
    ├─ crm.lead / crm.opportunity
    ├─ project.project / project.task
    └─ ir.model.access / ir.rule (security)
```

## Security Model

### Multi-Company Isolation
- Every CRM/Project record tagged with `company_id`
- OAuth token binds to specific user + company
- Server enforces `company_id` in all queries
- ir.rule applied at database level

### JWT Token Flow
1. Client registers app (RFC 7591 DCR) → `client_id`, `client_secret`
2. Client requests authorization code (user login)
3. Client exchanges code for access token (JWT)
4. Server validates JWT on every MCP call

### TLS/SSL
- Nginx reverse proxy on HTTPS (port 443)
- OAuth endpoints exposed at `/.well-known/oauth-*`
- MCP endpoint at `/mcp` (secure)

## Database Schema

### Key Models
- **res.company**: Company records (multi-company support)
- **res.partner**: Contacts (CRM data)
- **crm.lead / crm.opportunity**: Pipeline stages
- **project.project / project.task**: Project hierarchy
- **ir.model.access / ir.rule**: Security rules

### Indexes
- `idx_company_id` on all main models
- `idx_partner_company` on res.partner(company_id)
- `idx_lead_company` on crm.lead(company_id)

## API Endpoints

### OAuth
- `POST /.well-known/oauth/register` — DCR (register client)
- `GET /oauth/authorize` — User login & consent
- `POST /oauth/token` — Token exchange (code → JWT)

### MCP
- `GET /mcp` — MCP discovery
- `POST /mcp` — MCP calls (requires valid JWT)

## Testing

### Unit Tests
```bash
pytest tests/ -v
```

### Integration Tests
- CRM lead creation with company isolation
- Project task assignment + permissions
- OAuth token refresh & expiry

## Deployment

### Docker
```bash
docker build -t odoo-mcp-server .
docker run -e ODOO_URL=... -e ODOO_DB=... -p 443:443 odoo-mcp-server
```

### Nginx Configuration
See `nginx/` folder for SSL/TLS setup and reverse proxy config.

### Environment Variables
- `ODOO_URL`: Odoo instance URL
- `ODOO_DB`: Database name
- `JWT_SECRET`: Secret for signing tokens
- `MCP_PORT`: Server port (default 8000)

## Raven Discipline

### Security Checks (raven:odoo-guard)
- ✅ No hardcoded Odoo record IDs
- ✅ No raw SQL (use ORM + ir.rule)
- ✅ Multi-company rules enforced
- ✅ Security files present (ir.model.access.csv)

### Code Standards
- Python 3.13+ type hints required
- All ORM queries must include company filter
- JWT validation on every MCP call
- OAuth endpoints over HTTPS only

---

**Last Updated**: 2026-06-02  
**Owner**: giggso  
**Version**: 3.1.0-enterprise (Raven)
