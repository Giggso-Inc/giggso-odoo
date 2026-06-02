# Odoo MCP Server

**Connect Claude Desktop (and any MCP-compatible AI client) directly to your Odoo instance.**

Every tool call runs under the requesting user's real Odoo identity — not a service account.
`with_user(real_user)` ensures Odoo's own record rules and access lists enforce what each
person can see or change. No superuser path exists.

---

## What You Can Do

Ask Claude in plain English. The server translates to Odoo ORM calls:

> *"Show me all stale opportunities with no activity planned"*
> *"Create a task in the Q3 project and assign it to Sarah"*
> *"Schedule a follow-up call on this lead for Friday"*
> *"List all applicants for the Senior Engineer role"*
> *"Add a product line to quotation SO/2024/001"*
> *"Check me in to attendance"*

---

## Tool Inventory (44 tools)

### CRM — `crm.*` (8 tools)
| Tool | What it does |
|------|-------------|
| `crm_search_opportunities` | Search leads/opportunities by keyword |
| `crm_list_stale_opportunities` | Opportunities with no planned activity |
| `crm_list_stages` | All pipeline stages |
| `crm_create_lead` | Create a new CRM lead |
| `crm_add_note` | Add internal chatter note to a lead |
| `crm_update_stage` | Move lead to another pipeline stage |
| `crm_update_opportunity` | Edit name, revenue, probability, deadline, salesperson |
| `crm_schedule_activity` | Schedule To-Do / Email / Phone Call / Meeting |

### Projects — `project.*` (7 tools)
| Tool | What it does |
|------|-------------|
| `project_list_projects` | List visible projects |
| `project_list_tasks` | List tasks, filter by project |
| `project_list_task_stages` | All Kanban stages |
| `project_create_task` | Create a new task |
| `project_update_task` | Update name, description, deadline, priority, assignees |
| `project_move_task_stage` | Move task to another stage |
| `project_add_comment` | Add chatter comment to a task |

### HR / Employees — `hr.*` (3 tools)
| Tool | What it does |
|------|-------------|
| `hr_list_employees` | Search employees by name or department |
| `hr_get_employee` | Full employee record by ID |
| `hr_list_departments` | All departments |

### Recruiting — `recruit.*` (7 tools)
| Tool | What it does |
|------|-------------|
| `recruit_list_jobs` | Open job positions |
| `recruit_list_applicants` | Applicants, filtered by job or name |
| `recruit_list_applicant_stages` | Recruitment Kanban stages |
| `recruit_create_applicant` | Create a new applicant |
| `recruit_update_applicant` | Update name, contact, priority, recruiter |
| `recruit_move_applicant_stage` | Advance applicant through pipeline |
| `recruit_add_applicant_note` | Internal note on applicant |

### Sales — `sale.*` (6 tools)
| Tool | What it does |
|------|-------------|
| `sale_list_orders` | List orders/quotations, filter by state or partner |
| `sale_get_order` | Full order with all lines |
| `sale_list_products` | Search product catalogue by name or type |
| `sale_create_quotation` | Draft a new quotation |
| `sale_add_order_line` | Append a line to an existing draft order |
| `sale_confirm_order` | Confirm quotation → sale order |

### Attendance — `attendance.*` (4 tools)
| Tool | What it does |
|------|-------------|
| `attendance_check_in` | Clock in as current user |
| `attendance_check_out` | Clock out as current user |
| `attendance_list` | Attendance history with date range |
| `attendance_today_summary` | Today's check-in/out and hours |

### Expense — `expense.*` (4 tools)
| Tool | What it does |
|------|-------------|
| `expense_list` | List expenses for current user |
| `expense_create` | Log a new expense |
| `expense_list_sheets` | Expense report sheets |
| `expense_submit_sheet` | Submit a sheet for approval |

### Timesheet — `timesheet.*` (3 tools)
| Tool | What it does |
|------|-------------|
| `timesheet_list` | Timesheet entries by project/task/date |
| `timesheet_create_entry` | Log hours on a task |
| `timesheet_weekly_summary` | This week's hours by project |

### Admin — `admin.*` (2 tools)
| Tool | What it does |
|------|-------------|
| `odoo_health_check` | Server + Odoo connectivity status |
| `odoo_list_allowed_capabilities` | Which modules are enabled for your account |

---

## Architecture

```
Claude Desktop / Claude.ai / Cursor
        │
        │  HTTPS :443  (Bearer OAuth token)
        ▼
┌─────────────────────────────────┐
│  nginx  (TLS termination)       │
│  docker container               │
└────────────────┬────────────────┘
                 │  HTTP :8443  (docker-internal)
                 ▼
┌─────────────────────────────────┐
│  odoo-mcp  (FastMCP + OAuth)    │
│  - RFC 7591 Dynamic Client Reg  │
│  - Authorization-code flow      │
│  - Bearer token validation      │
│  - HMAC request signing         │
└────────────────┬────────────────┘
                 │  HTTPS JSON-RPC  (signing secret)
                 ▼
┌─────────────────────────────────┐
│  Odoo MCP Connector  (addon)    │
│  - Verifies HMAC signature      │
│  - Maps email → res.users       │
│  - Executes ORM as real user    │
│  - Writes audit log             │
└────────────────┬────────────────┘
                 │  with_user(real_user)
                 ▼
        Odoo  (PostgreSQL)
```

**Security layers:**
- TLS everywhere — nginx terminates public TLS; MCP container never touches the internet directly
- OAuth 2.0 authorization-code flow — users log in with Odoo credentials, not shared keys
- RFC 7591 Dynamic Client Registration — Claude Desktop auto-registers without manual client setup
- HMAC signing — every MCP→Odoo request is signed; the addon rejects unsigned calls
- `with_user(real_user)` — Odoo's own ir.rule and access control apply; no privilege escalation
- Audit log — every write action logged to `/var/log/odoo-mcp/audit.jsonl`

---

## Quick Deploy

**Requirements:** OCI VM (or any Linux host), Docker + Docker Compose, Odoo instance reachable from the VM.

### 1. Clone and configure

```bash
git clone https://github.com/giggsoinc/giggso-odoo.git
cd giggso-odoo/deploy
cp .env.example .env
# Edit .env — set ODOO_URL, ODOO_DB_NAME, certs path, public URL
```

### 2. Start the stack

```bash
docker compose --profile nginx up -d
```

### 3. Install the Odoo addon

```
Odoo → Apps → Update Apps List → Install "Odoo MCP Connector"
Settings → Technical → System Parameters
  → odoo_mcp_connector.signing_secret = <value from deploy/.env>
```

### 4. Verify

```bash
curl https://odoo-mcp.yourdomain.com/.well-known/openid-configuration
# expected: JSON with issuer, authorization_endpoint, token_endpoint
```

See [README-DEPLOY.md](README-DEPLOY.md) for the full step-by-step with firewall rules, cert setup, and rollback.

---

## Client Setup — Claude Desktop

1. Install [mcp-remote](https://www.npmjs.com/package/mcp-remote): `npm install -g mcp-remote`
2. Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "mcp-remote",
      "args": ["https://odoo-mcp.yourdomain.com", "--transport", "streamable-http"]
    }
  }
}
```

3. Restart Claude Desktop — it will open a browser to complete Odoo login
4. Start talking to your Odoo data

See [README-USER.md](README-USER.md) for the full walkthrough including Claude.ai and Cursor setup.

---

## Identity & Security Model

- **No shared credentials** — each user authenticates with their own Odoo login
- **Token-scoped** — the OAuth token identifies the user; the server looks up their `res.users` record
- **Record rules enforced** — `ir.rule` and model access lists apply exactly as in the Odoo UI
- **Multi-company safe** — `company_id` filters applied; cross-company data never leaks
- **Audit trail** — every create/write/action logged with actor, model, record ID, and timestamp

---

## Documentation Index

| Doc | Audience | Content |
|-----|----------|---------|
| [README-DEPLOY.md](README-DEPLOY.md) | Operators | Full deploy: addon install, Docker stack, TLS, smoke tests, rollback |
| [README-DEBUG.md](README-DEBUG.md) | Operators | Failure playbook — M1–M5 MCP failures, O1–O6 Odoo issues |
| [README-USER.md](README-USER.md) | End users | Connect Claude Desktop / Claude.ai, first prompts, troubleshooting |
| [README-CRM.md](README-CRM.md) | End users | 8 CRM tools with params and example prompts |
| [README-PROJECT.md](README-PROJECT.md) | End users | 7 Project tools with params and example prompts |
| [README-RECRUIT.md](README-RECRUIT.md) | End users | 7 Recruitment tools |
| [README-HR.md](README-HR.md) | End users | 3 HR / Employee read tools |
| [README-ATTENDANCE.md](README-ATTENDANCE.md) | End users | 4 Attendance tools (clock in/out) |
| [README-EXPENSE.md](README-EXPENSE.md) | End users | 4 Expense tools |
| [README-TIMESHEET.md](README-TIMESHEET.md) | End users | 3 Timesheet tools |
| [README-SALE.md](README-SALE.md) | End users | 6 Sales tools (orders, products, quotations) |
| [docs/architecture.md](docs/architecture.md) | Architects | ADRs: bearer auth, nginx sidecar, roadmap |
| [docs/operator-runbook.md](docs/operator-runbook.md) | Operators | Token issuance, revocation, log tailing, cert rotation |
| [ROADMAP.md](ROADMAP.md) | All | Upcoming: group permissions, Workspace SSO |

---

## Stack

| Component | Technology |
|-----------|-----------|
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) + Uvicorn |
| Transport | Streamable HTTP (MCP spec) |
| Auth | OAuth 2.0 + RFC 7591 DCR |
| TLS frontend | nginx 1.25 |
| Runtime | Python 3.13, Docker |
| Odoo addon | Odoo 17 / 18 / 19 compatible |
| Deployment | OCI VM / any Linux host with Docker |

---

## Repository Layout

```
giggso-odoo/
├── odoo_mcp_server/          # FastMCP server (Python package)
│   └── src/odoo_mcp/
│       ├── tools/            # One file per domain (crm, projects, sale …)
│       ├── oauth*.py         # OAuth/DCR flow
│       ├── server.py         # Entry point + uvicorn config
│       └── config.py         # Settings via env vars
├── odoo_addons/
│   └── odoo_mcp_connector/   # Odoo addon (installed in your Odoo)
│       └── controllers/      # HMAC-verified HTTP actions per domain
├── deploy/                   # Docker Compose stack + nginx config
│   ├── docker-compose.yml
│   ├── nginx/conf.d/
│   └── .env.example
├── Client_Install_Scripts/   # mcp-remote token helpers for end users
└── docs/                     # Architecture decisions, runbooks
```

---

## License

MIT — see [LICENSE](LICENSE) if present, otherwise contact [giggso.ravi@gmail.com](mailto:giggso.ravi@gmail.com).
