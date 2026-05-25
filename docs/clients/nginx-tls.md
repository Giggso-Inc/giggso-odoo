# TLS termination for the Odoo MCP server (existing nginx)

**Version:** Cycle 2 · 2026-05-25
**Audience:** ops on the EC2 host running `odoo.giggso.com`
**Scope:** put nginx in front of the FastMCP service so Claude Desktop sees a
real, publicly trusted certificate instead of the self-signed one served
directly by uvicorn on `:8443`.

---

## Why this matters

Claude Desktop (and the `mcp-remote` bridge it runs) hard-rejects any TLS
handshake that does not chain to a trusted root. The self-signed cert that
uvicorn currently serves works for curl with `-k` but **will never work for
Claude**. There is no client-side override.

The fix is the same pattern you are already running for Odoo itself:
nginx terminates TLS with the real cert, then proxies cleartext HTTP to the
MCP service on localhost.

We are **not** adding Cloudflare, Caddy, or certbot. You already have
`/home/opc/gg-odoo-app/domaincert/nginx.crt` and `nginx.key` — we reuse them.

---

## Target topology

```
Claude Desktop  ──HTTPS (443)──▶  nginx on EC2  ──HTTP (8443→127.0.0.1)──▶  uvicorn (FastMCP)
                                  cert: nginx.crt/.key
                                  server_name: odoo.giggso.com
```

The MCP container/process keeps listening on `:8443` but **only on the loopback
interface**. Public traffic enters nginx on `:443`.

---

## Step 1 — Bind uvicorn to localhost only

In `odoo_mcp_server/.env` (or wherever `Settings` is sourced from):

```ini
# Bind only to loopback; nginx fronts public TLS.
HOST=127.0.0.1
PORT=8443

# Disable the self-signed cert path — nginx terminates TLS now.
# Leave both blank to fall back to plain HTTP on the loopback.
TLS_CERT_FILE=
TLS_KEY_FILE=

# Public URL must match the cert and what Claude Desktop will hit.
PUBLIC_URL=https://odoo.giggso.com
```

Restart the MCP service. Confirm it is loopback-only:

```bash
sudo ss -ltnp | grep 8443
# expected: 127.0.0.1:8443  (NOT 0.0.0.0:8443)
```

If you see `0.0.0.0:8443`, the public port is still exposed — fix HOST and
restart before continuing.

---

## Step 2 — Add the MCP server block to nginx

Drop this into `/etc/nginx/conf.d/odoo-mcp.conf` (or merge into the existing
`odoo.giggso.com` server block — both work). The path-based variant below
keeps Odoo on `/` and MCP on `/mcp/`, which is the lowest-risk option
because it shares one cert and one hostname.

```nginx
# /etc/nginx/conf.d/odoo-mcp.conf
# Reuses the existing odoo.giggso.com certificate.

server {
    listen 443 ssl http2;
    server_name odoo.giggso.com;

    ssl_certificate     /home/opc/gg-odoo-app/domaincert/nginx.crt;
    ssl_certificate_key /home/opc/gg-odoo-app/domaincert/nginx.key;

    # Standard hardening. Adjust to match your other server blocks.
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;

    # ── MCP server (FastMCP + headless bearer routes) ───────────────
    # Everything under /mcp/ is proxied to the local uvicorn process.
    # SSE needs a long read timeout and disabled buffering.
    location /mcp/ {
        proxy_pass         http://127.0.0.1:8443/;
        proxy_http_version 1.1;

        # Pass through identity for upstream logging.
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;

        # SSE / streamable-HTTP requirements.
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;

        # Required for SSE keepalive through nginx.
        proxy_set_header Connection "";
    }

    # ── Odoo itself ─────────────────────────────────────────────────
    # Leave your existing Odoo location blocks here, unchanged.
    # location / { proxy_pass http://127.0.0.1:8069; ... }
}
```

After saving:

```bash
sudo nginx -t                 # syntax check
sudo systemctl reload nginx   # zero-downtime reload
```

---

## Step 3 — Update PUBLIC_URL to match the path prefix

Because we mounted MCP under `/mcp/`, update the MCP service env:

```ini
PUBLIC_URL=https://odoo.giggso.com/mcp
```

Then restart the MCP service. The OAuth metadata documents and the JWT
`iss`/`aud` claims will then resolve to the same URL Claude Desktop calls.

If you prefer a dedicated subdomain (`mcp.giggso.com`) later, swap the
`server_name` and add a DNS A record — the proxy block stays identical and
the cert can be reissued to cover both names.

---

## Step 4 — Verify

From your laptop (not the EC2 host):

```bash
# 1. Public TLS handshake must validate without -k.
curl -sS https://odoo.giggso.com/mcp/.well-known/oauth-authorization-server | head

# 2. Bearer flow should work end-to-end.
curl -sS -X POST https://odoo.giggso.com/mcp/auth/issue-token \
  -H 'Content-Type: application/json' \
  -d '{"login":"YOU@giggso.com","password":"…","label":"smoke"}'
```

Both should return JSON, not certificate errors and not 502s. If you see
502, nginx reached uvicorn but uvicorn rejected — check the service logs.
If you see `SSL_ERROR`, the cert path in nginx is wrong.

---

## Rollback

If anything goes wrong, restore direct exposure in one step:

```bash
sudo rm /etc/nginx/conf.d/odoo-mcp.conf
sudo systemctl reload nginx
# Set HOST=0.0.0.0 and TLS_CERT_FILE/TLS_KEY_FILE back in .env
# Restart MCP service.
```

Self-signed direct exposure is fine for curl-based testing while we
diagnose; it just won't work for Claude Desktop.

---

## Known limits (deferred to Cycle 3)

- No automatic cert renewal hook here — your existing cert lifecycle applies.
- No separate access log for MCP traffic; it lands in the main nginx access log.
- No rate limiting at the nginx layer — Cycle 3 will add `limit_req_zone`
  in front of `/mcp/auth/issue-token` to slow credential-stuffing attempts.
