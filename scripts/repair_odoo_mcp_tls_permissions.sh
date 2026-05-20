#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/giggso-odoo}"
DEPLOY_DIR="$REPO_DIR/deploy"
CERT_DIR="$DEPLOY_DIR/certs"
AUDIT_DIR="$DEPLOY_DIR/audit"
ENV_FILE="$DEPLOY_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

get_env_value() {
  local name="$1"
  grep -E "^${name}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-
}

uid="$(get_env_value ODOO_MCP_RUN_UID)"
gid="$(get_env_value ODOO_MCP_RUN_GID)"

if [ -z "$uid" ] || [ -z "$gid" ]; then
  echo "ODOO_MCP_RUN_UID and ODOO_MCP_RUN_GID must be set in $ENV_FILE" >&2
  exit 1
fi

sudo mkdir -p "$CERT_DIR" "$AUDIT_DIR"

if [ ! -f "$CERT_DIR/tls.crt" ] || [ ! -f "$CERT_DIR/tls.key" ]; then
  echo "Missing TLS files under $CERT_DIR" >&2
  echo "Expected: tls.crt and tls.key" >&2
  exit 1
fi

sudo chown "$uid:$gid" "$CERT_DIR" "$CERT_DIR/tls.crt" "$CERT_DIR/tls.key" "$AUDIT_DIR"
sudo chmod 750 "$CERT_DIR" "$AUDIT_DIR"
sudo chmod 644 "$CERT_DIR/tls.crt"
sudo chmod 640 "$CERT_DIR/tls.key"

if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
  sudo chcon -Rt svirt_sandbox_file_t "$CERT_DIR" "$AUDIT_DIR"
fi

echo "Repaired MCP TLS permissions:"
sudo ls -ldZ "$CERT_DIR" "$AUDIT_DIR" 2>/dev/null || sudo ls -ld "$CERT_DIR" "$AUDIT_DIR"
sudo ls -lZ "$CERT_DIR/tls.crt" "$CERT_DIR/tls.key" 2>/dev/null || sudo ls -l "$CERT_DIR/tls.crt" "$CERT_DIR/tls.key"
