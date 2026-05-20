#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/giggso-odoo}"
DEPLOY_DIR="$REPO_DIR/deploy"
SERVICE="${SERVICE:-odoo-mcp}"

if [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
  echo "Missing docker-compose.yml at $DEPLOY_DIR" >&2
  exit 1
fi

cd "$DEPLOY_DIR"

echo "Host cert permissions:"
ls -ldZ certs 2>/dev/null || ls -ld certs
ls -lZ certs/tls.crt certs/tls.key 2>/dev/null || ls -l certs/tls.crt certs/tls.key

echo
echo "Compose user:"
docker compose config | sed -n "/${SERVICE}:/,/^[^[:space:]]/p" | grep -E "user:|source:|target:|read_only|bind:" || true

echo
echo "Container TLS access check:"
docker compose run --rm --entrypoint sh "$SERVICE" -lc '
  echo "id=$(id)"
  ls -ld /run /run/odoo-mcp /run/odoo-mcp/certs
  ls -l /run/odoo-mcp/certs/tls.crt /run/odoo-mcp/certs/tls.key
  test -r /run/odoo-mcp/certs/tls.crt && echo "cert readable: yes" || echo "cert readable: no"
  test -r /run/odoo-mcp/certs/tls.key && echo "key readable: yes" || echo "key readable: no"
'
