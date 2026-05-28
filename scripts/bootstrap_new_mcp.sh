#!/usr/bin/env bash
#
# bootstrap_new_mcp.sh
#
# Summary:
#   One-shot from-scratch bootstrap of the Giggso Odoo MCP server on a clean
#   Oracle Linux 9 VM, accessible at https://odoo-mcp.giggso.com on the
#   standard HTTPS port 443 (lesson learned: Anthropic cloud connectors
#   only reach port 443).
#
#   Run this from your Mac. It will:
#     1. SCP the wildcard *.giggso.com cert from OLD VM to your Mac (/tmp)
#     2. SCP cert from your Mac to NEW VM
#     3. SSH to NEW VM and run the install (docker, repo, .env, nginx, MCP)
#     4. Verify the public discovery endpoint is live
#
# Version: 0.1.0
# Execution context: macOS bash/zsh, requires ssh + scp on PATH
#
# Usage:
#   chmod +x bootstrap_new_mcp.sh
#   ./bootstrap_new_mcp.sh

set -euo pipefail

# ── Config (edit only if these change) ──────────────────────────────────
KEY="$HOME/.ssh/odoo-mcp-server.pem"
OLD_HOST="opc@64.181.194.210"
NEW_HOST="opc@147.224.143.159"
DOMAIN="odoo-mcp.giggso.com"
ODOO_URL="https://odoo.giggso.com"
ODOO_DB="gg-odoo-db"
REPO="https://github.com/giggsoinc/giggso-odoo.git"

# Local staging dir — held briefly, cleaned at end.
STAGE="/tmp/giggso-cert-$(date +%s)"

echo "==========================================="
echo "  Giggso MCP — Clean VM Bootstrap"
echo "==========================================="
echo "  OLD: $OLD_HOST  (cert source)"
echo "  NEW: $NEW_HOST  (target)"
echo "  Domain: $DOMAIN"
echo ""

# ── Step 1: pull cert from OLD ──────────────────────────────────────────
# nginx.key is root-readable only, so sudo on OLD; we tar+stream so we
# only need one ssh roundtrip and the key never sits on the OLD filesystem
# in a non-root location.
echo ">> [1/5] Copying wildcard cert from OLD VM..."
mkdir -p "$STAGE"
ssh -i "$KEY" "$OLD_HOST" \
    'sudo tar -C /home/opc/gg-odoo-app/domaincert -cf - nginx.crt nginx.key' \
    | tar -C "$STAGE" -xf -
ls -la "$STAGE"

# ── Step 2: push cert to NEW ────────────────────────────────────────────
# /home/opc/certs is the canonical cert location on the NEW VM; nginx
# container will mount it read-only.
echo ""
echo ">> [2/5] Pushing cert to NEW VM..."
ssh -i "$KEY" "$NEW_HOST" 'mkdir -p /home/opc/certs'
scp -i "$KEY" "$STAGE/nginx.crt" "$STAGE/nginx.key" "$NEW_HOST:/home/opc/certs/"
ssh -i "$KEY" "$NEW_HOST" 'chmod 600 /home/opc/certs/nginx.key && chmod 644 /home/opc/certs/nginx.crt'

# ── Step 3: install docker + clone + build on NEW ───────────────────────
# Single remote heredoc keeps this idempotent — re-running the bootstrap
# on the same VM should be safe.
echo ""
echo ">> [3/5] Installing Docker + cloning repo on NEW VM..."
ssh -i "$KEY" "$NEW_HOST" "DOMAIN='$DOMAIN' ODOO_URL='$ODOO_URL' ODOO_DB='$ODOO_DB' REPO='$REPO' bash -s" <<'REMOTE'
set -euo pipefail

# Docker install — Oracle Linux 9 uses the docker-ce repo.
if ! command -v docker >/dev/null 2>&1; then
    echo "  Installing Docker..."
    sudo dnf -y install dnf-plugins-core
    sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable --now docker
    sudo usermod -aG docker opc
fi

# Open firewall port 443 (Oracle Linux 9 uses firewalld by default).
if command -v firewall-cmd >/dev/null 2>&1; then
    sudo firewall-cmd --permanent --add-port=443/tcp 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
fi

# Clone or update repo.
if [ ! -d /home/opc/giggso-odoo ]; then
    git clone "$REPO" /home/opc/giggso-odoo
else
    (cd /home/opc/giggso-odoo && git pull)
fi
cd /home/opc/giggso-odoo

# Generate .env for the deploy. Public URL has NO :port suffix and NO
# /mcp prefix — MCP mounts at host root so OAuth discovery works at
# https://odoo-mcp.giggso.com/.well-known/...
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
# ODOO_MCP_TRANSPORT=sse is REQUIRED — without it, the container
# defaults to stdio mode, reads JSON-RPC from stdin, crashes immediately.
# Cost us an hour to find the first time. Always include it.
cat > deploy/.env <<EOF
ODOO_URL=$ODOO_URL
ODOO_DB_NAME=$ODOO_DB
ODOO_MCP_PUBLIC_URL=https://$DOMAIN
ODOO_MCP_CONNECTOR_SECRET=$SECRET
ODOO_MCP_TRANSPORT=sse
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8443
ODOO_MCP_TLS_CERT_FILE=
ODOO_MCP_TLS_KEY_FILE=
MCP_NGINX_HOST_PORT=443
MCP_NGINX_CERT_DIR=/home/opc/certs
MCP_NGINX_CERT_FILE=nginx.crt
MCP_NGINX_KEY_FILE=nginx.key
EOF

echo "  .env written. Secret length: $(grep CONNECTOR_SECRET deploy/.env | wc -c)"
REMOTE

# ── Step 4: write nginx conf + start stack ──────────────────────────────
echo ""
echo ">> [4/5] Generating nginx conf and starting MCP + nginx..."
ssh -i "$KEY" "$NEW_HOST" "DOMAIN='$DOMAIN' bash -s" <<'REMOTE'
set -euo pipefail
cd /home/opc/giggso-odoo

# Nginx config: MCP mounted at host ROOT (no /mcp prefix) — OAuth
# discovery + SSE + everything served from /. Clean, simple, port 443.
sudo mkdir -p deploy/nginx/conf.d
sudo tee deploy/nginx/conf.d/odoo-mcp.conf > /dev/null <<EOF
server {
    listen 443 ssl;
    http2 on;
    server_name $DOMAIN;

    ssl_certificate     /etc/nginx/certs/nginx.crt;
    ssl_certificate_key /etc/nginx/certs/nginx.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass         http://odoo-mcp:8443;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
        proxy_set_header   Connection "";
    }
}
EOF

# Start MCP + nginx with sg trick so docker group works without re-login.
cd deploy
sg docker -c "docker compose --profile nginx up -d --build"

echo ""
echo "  Containers:"
sg docker -c "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
REMOTE

# ── Step 5: verify ──────────────────────────────────────────────────────
echo ""
echo ">> [5/5] Verifying public OAuth discovery endpoint..."
sleep 5
RESP=$(curl -s "https://$DOMAIN/.well-known/oauth-authorization-server" || echo "FAIL")
if echo "$RESP" | grep -q "registration_endpoint"; then
    echo "  SUCCESS: discovery endpoint live at https://$DOMAIN"
    echo "$RESP" | python3 -m json.tool | head -10
else
    echo "  WARNING: discovery did not return expected JSON. Got:"
    echo "$RESP"
    echo "  -> SSH to NEW and check: docker logs deploy-nginx-1 ; docker logs deploy-odoo-mcp-1"
fi

# Clean up local cert staging.
rm -rf "$STAGE"

echo ""
echo "==========================================="
echo "  Bootstrap complete."
echo ""
echo "  Test in Claude Desktop:"
echo "    Settings -> Connectors -> Add Custom"
echo "    URL: https://$DOMAIN"
echo "==========================================="
