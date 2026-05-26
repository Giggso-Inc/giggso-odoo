#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# scripts/lib/direct-mode.sh — TLS cert management and .env for direct mode
#
# Summary:
#   Provides generate_tls_cert(), write_env(), and start_docker() for
#   the direct frontend mode (Cycle 1 style: uvicorn binds 0.0.0.0:8443
#   with its own TLS certificate). These functions are NOT used in nginx
#   sidecar mode — install_nginx_frontend.sh provides its own write_env
#   variant there.
#
# Version: 1.0.0
# Sourced by: scripts/install_odoo_mcp.sh (direct mode path only)
# ─────────────────────────────────────────────────────────────────────

# ── secure_tls_cert_permissions ───────────────────────────────────────
# Locks down the cert directory and files so only the MCP run user can
# read the private key. Avoids world-readable key material on disk.
secure_tls_cert_permissions() {
  sudo chown "$MCP_RUN_UID:$MCP_RUN_GID" "$1" "$2" "$3"
  sudo chmod 750 "$1"
  sudo chmod 644 "$2"
  sudo chmod 640 "$3"
}

# ── generate_tls_cert ────────────────────────────────────────────────
# Copies existing host certs if found; otherwise generates a self-signed
# cert. Either way, fixes permissions so uvicorn can read the key.
generate_tls_cert() {
  local cert_dir="$REPO_DIR/deploy/certs"
  local cert_file="$cert_dir/tls.crt"
  local key_file="$cert_dir/tls.key"

  if [ -f "$cert_file" ] && [ -f "$key_file" ]; then
    secure_tls_cert_permissions "$cert_dir" "$cert_file" "$key_file"
    return
  fi

  # Prefer copying from an existing host cert (e.g. Let's Encrypt or OCI-managed).
  if [ -f "$MCP_TLS_SOURCE_CERT_FILE" ] && [ -f "$MCP_TLS_SOURCE_KEY_FILE" ]; then
    sudo mkdir -p "$cert_dir"
    sudo cp "$MCP_TLS_SOURCE_CERT_FILE" "$cert_file"
    sudo cp "$MCP_TLS_SOURCE_KEY_FILE" "$key_file"
    secure_tls_cert_permissions "$cert_dir" "$cert_file" "$key_file"
    return
  fi

  # Last resort: generate a self-signed cert for the public URL hostname/IP.
  command -v openssl >/dev/null 2>&1 || { echo "openssl required for TLS cert generation" >&2; exit 1; }
  sudo mkdir -p "$cert_dir"
  sudo chown "$MCP_RUN_UID:$MCP_RUN_GID" "$cert_dir"
  sudo chmod 750 "$cert_dir"

  local host_name san
  host_name="${MCP_PUBLIC_URL#*://}"; host_name="${host_name%%/*}"
  [[ "$host_name" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    && san="IP:${host_name}" || san="DNS:${host_name}"

  sudo openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$key_file" -out "$cert_file" -days 365 \
    -subj "/CN=${host_name}" -addext "subjectAltName=${san}" >/dev/null 2>&1
  secure_tls_cert_permissions "$cert_dir" "$cert_file" "$key_file"
}

# ── write_env ─────────────────────────────────────────────────────────
# Writes deploy/.env for direct mode. ODOO_MCP_TLS_CERT_FILE and KEY
# point to the real cert paths — unlike nginx mode which sets them empty.
write_env() {
  mkdir -p "$REPO_DIR/deploy/audit"
  umask 077
  cat > "$REPO_DIR/deploy/.env" <<EOF
ODOO_URL=$ODOO_URL
ODOO_DB_NAME=$ODOO_DB_NAME
ODOO_MCP_CONNECTOR_SECRET=$CONNECTOR_SECRET
ODOO_MCP_IDENTITY_ISSUER=$IDENTITY_ISSUER
ODOO_MCP_IDENTITY_AUDIENCE=$IDENTITY_AUDIENCE
ODOO_MCP_IDENTITY_JWKS_URL=$IDENTITY_JWKS_URL
ODOO_MCP_AUDIT_LOG=/var/log/odoo-mcp/audit.jsonl
ODOO_MCP_TRANSPORT=sse
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8443
ODOO_MCP_BIND=$MCP_BIND
ODOO_MCP_RUN_UID=$MCP_RUN_UID
ODOO_MCP_RUN_GID=$MCP_RUN_GID
ODOO_MCP_PUBLIC_URL=$MCP_PUBLIC_URL
ODOO_MCP_TLS_CERT_FILE=$MCP_TLS_CERT_FILE
ODOO_MCP_TLS_KEY_FILE=$MCP_TLS_KEY_FILE
EOF
}

# ── start_docker ──────────────────────────────────────────────────────
# Builds and starts the odoo-mcp container in direct mode (no nginx profile).
start_docker() {
  [ "${SKIP_DOCKER_START:-0}" = "1" ] && return
  if command -v docker >/dev/null 2>&1; then
    (cd "$REPO_DIR/deploy" && docker compose up -d --build)
  else
    echo "Docker not found. Install Docker or run the MCP server manually."
  fi
}
