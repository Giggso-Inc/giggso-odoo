# Operator Runbook — Odoo MCP Server

Daily operations for whoever runs the OCI box (Ravi or a designated backup).

---

## Issue a token for a teammate

```bash
curl -sS -X POST https://odoo.giggso.com:9443/mcp/auth/issue-token \
  -H 'Content-Type: application/json' \
  -d '{
        "login":    "teammate@giggso.com",
        "password": "THEIR_ODOO_PASSWORD",
        "label":    "claude-desktop-macbook"
      }'
```

Send the teammate the `token` value from the response. Tell them to treat it like a password.

---

## Revoke a token

First find the token's `jti` (JWT ID) from the audit log or from the `whoami` endpoint.
Then:

```bash
curl -sS -X POST https://odoo.giggso.com:9443/mcp/auth/revoke \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"jti": "abc123..."}'
```

---

## Read the audit log

```bash
sudo tail -f /var/log/odoo-mcp/audit.jsonl
```

Or filter for a specific user:
```bash
sudo grep '"subject":"12"' /var/log/odoo-mcp/audit.jsonl | tail -20
```

The log is mounted from `deploy/audit/` on the host into the container at `/var/log/odoo-mcp/`.

---

## Restart safely

```bash
cd /home/opc/giggso-odoo/deploy
sudo docker compose --profile nginx restart
```

To rebuild after a code change:
```bash
sudo docker compose --profile nginx up -d --build odoo-mcp
```

---

## Rotate the connector secret

Rotating breaks all in-flight sessions until the Odoo system parameter is updated.
Do this during low-traffic periods.

1. Generate a new secret:
   ```bash
   openssl rand -hex 32
   ```
2. Update the Odoo system parameter:
   - Settings -> Technical -> Parameters -> System Parameters
   - Set `odoo_mcp_connector.signing_secret` to the new value
3. Update `deploy/.env` on the box:
   ```bash
   sudo nano /home/opc/giggso-odoo/deploy/.env
   # Update ODOO_MCP_CONNECTOR_SECRET=<new-value>
   ```
4. Restart the MCP container:
   ```bash
   cd /home/opc/giggso-odoo/deploy
   sudo docker compose --profile nginx up -d odoo-mcp
   ```

---

## Where things live

| Thing | Location |
|---|---|
| Repo | `/home/opc/giggso-odoo/` |
| Deploy config | `/home/opc/giggso-odoo/deploy/.env` |
| TLS certificates | `/home/opc/gg-odoo-app/domaincert/` (nginx.crt, nginx.key) |
| nginx conf | `/home/opc/giggso-odoo/deploy/nginx/conf.d/odoo-mcp.conf` |
| Audit log | `/home/opc/giggso-odoo/deploy/audit/audit.jsonl` |
| Container logs | `sudo docker compose logs -f odoo-mcp` |

---

## If certificates expire

The nginx sidecar bind-mounts `/home/opc/gg-odoo-app/domaincert/` at runtime.
Replace `nginx.crt` and `nginx.key` in that directory, then:

```bash
cd /home/opc/giggso-odoo/deploy
sudo docker compose --profile nginx restart nginx
```

No rebuild needed — nginx re-reads certs on startup.
