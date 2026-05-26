# Claude Desktop — Odoo MCP Setup

Connect Claude Desktop to the Odoo MCP server in four steps.
Every tool call runs under your Odoo identity.

---

## Step 1 — Open OCI firewall port 9443

In the Oracle Cloud console:

1. Navigate to the instance's VCN -> Security Lists (or Network Security Groups).
2. Add an ingress rule: TCP, source 0.0.0.0/0, destination port 9443.
3. Also add the port to the instance's OS firewall:
   ```bash
   sudo firewall-cmd --permanent --add-port=9443/tcp
   sudo firewall-cmd --reload
   ```

Verify the port is reachable from your laptop before proceeding:
```bash
curl -k https://odoo.giggso.com:9443/mcp/auth/whoami
# Expected: HTTP 401 {"detail":"Authorization header missing"}
```

---

## Step 2 — Mint a bearer token

Run this from your laptop (replace the placeholders):

```bash
curl -sS -X POST https://odoo.giggso.com:9443/mcp/auth/issue-token \
  -H 'Content-Type: application/json' \
  -d '{
        "login":    "you@giggso.com",
        "password": "YOUR_ODOO_PASSWORD",
        "label":    "claude-desktop-laptop"
      }'
```

Expected response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 7776000,
  "label": "claude-desktop-laptop"
}
```

Smoke-test the token before wiring Claude:
```bash
TOKEN='eyJhbGciOiJIUzI1NiIs...'
curl -sS https://odoo.giggso.com:9443/mcp/auth/whoami \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"subject":"12","email":"you@giggso.com","scopes":[]}
```

If `whoami` returns 401, stop and re-issue the token. Do not proceed until `whoami` succeeds.

---

## Step 3 — Edit claude_desktop_config.json

Config file location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add or merge this block:

```json
{
  "mcpServers": {
    "odoo-giggso": {
      "type": "sse",
      "url": "https://odoo.giggso.com:9443/mcp/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

Replace `YOUR_TOKEN_HERE` with the token from Step 2. Treat the token like a password.

---

## Step 4 — Restart Claude Desktop and smoke-test

Fully quit and reopen Claude Desktop (Cmd+Q on macOS, not just close the window).

Try these queries in a new conversation:

- "What tools do you have from odoo?"
- "Search CRM opportunities"
- "Create a lead called Acme MCP Smoke with revenue 50000"

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Token expired or invalid | Re-mint token via Step 2 |
| `502 Bad Gateway` | nginx sidecar can't reach odoo-mcp container | `sudo docker compose logs nginx odoo-mcp` on the EC2 box |
| `Connection refused` | OCI port 9443 not open | Repeat Step 1 |
| Tools not listed | Claude Desktop version too old | Update to 0.9 or newer |

For detailed logs: see [docs/operator-runbook.md](../operator-runbook.md).
