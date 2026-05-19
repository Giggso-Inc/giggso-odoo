#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/giggsoinc/giggso-odoo.git"
REPO_DIR="${REPO_DIR:-$HOME/giggso-odoo}"
ODOO_ADDONS_DIR="${ODOO_ADDONS_DIR:-/opt/odoo/custom_addons}"
ODOO_CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
ODOO_URL="${ODOO_URL:-}"
MCP_BIND="${MCP_BIND:-0.0.0.0}"
MCP_PUBLIC_URL="${MCP_PUBLIC_URL:-}"
MCP_TLS_CERT_FILE="${MCP_TLS_CERT_FILE:-/run/odoo-mcp/certs/tls.crt}"
MCP_TLS_KEY_FILE="${MCP_TLS_KEY_FILE:-/run/odoo-mcp/certs/tls.key}"
IDENTITY_ISSUER="${IDENTITY_ISSUER:-}"
IDENTITY_AUDIENCE="${IDENTITY_AUDIENCE:-odoo-mcp}"
IDENTITY_JWKS_URL="${IDENTITY_JWKS_URL:-}"
CONNECTOR_SECRET="${CONNECTOR_SECRET:-}"
SKIP_GIT_CLONE="${SKIP_GIT_CLONE:-0}"
SKIP_ODOO_CONFIG_EDIT="${SKIP_ODOO_CONFIG_EDIT:-0}"
SKIP_DOCKER_START="${SKIP_DOCKER_START:-0}"

usage() {
  cat <<'USAGE'
Install Giggso Odoo MCP on an open-source Odoo server.

Run from anywhere:
  bash scripts/install_odoo_mcp.sh

Or without prompts:
  ODOO_URL=https://odoo.example.com \
  IDENTITY_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0 \
  IDENTITY_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys \
  MCP_PUBLIC_URL=https://mcp.example.com \
  bash scripts/install_odoo_mcp.sh

Useful overrides:
  REPO_DIR=$HOME/giggso-odoo
  ODOO_ADDONS_DIR=/opt/odoo/custom_addons
  ODOO_CONFIG=/etc/odoo/odoo.conf
  ODOO_SERVICE=odoo
  MCP_BIND=0.0.0.0
  MCP_PUBLIC_URL=https://64.181.194.210
  IDENTITY_AUDIENCE=odoo-mcp
  CONNECTOR_SECRET=<existing-secret>
  SKIP_GIT_CLONE=1
  SKIP_ODOO_CONFIG_EDIT=1
  SKIP_DOCKER_START=1
USAGE
}

select_identity_defaults() {
  if [ -n "$IDENTITY_ISSUER" ] || [ -n "$IDENTITY_JWKS_URL" ]; then
    return
  fi
  echo "Identity provider:"
  echo "  1) Google Cloud / Google Workspace"
  echo "  2) Microsoft Entra ID"
  echo "  3) Okta"
  echo "  4) Custom OIDC"
  read -r -p "Select [1-4, default 1]: " provider
  provider="${provider:-1}"
  case "$provider" in
    1)
      IDENTITY_ISSUER="https://accounts.google.com"
      IDENTITY_JWKS_URL="https://www.googleapis.com/oauth2/v3/certs"
      ;;
    2)
      read -r -p "Microsoft tenant ID: " tenant_id
      IDENTITY_ISSUER="https://login.microsoftonline.com/${tenant_id}/v2.0"
      IDENTITY_JWKS_URL="https://login.microsoftonline.com/${tenant_id}/discovery/v2.0/keys"
      ;;
    3)
      read -r -p "Okta domain, e.g. https://yourcompany.okta.com: " okta_domain
      IDENTITY_ISSUER="${okta_domain%/}/oauth2/default"
      IDENTITY_JWKS_URL="${okta_domain%/}/oauth2/default/v1/keys"
      ;;
    *)
      ;;
  esac
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

prompt_if_empty() {
  local var_name="$1"
  local prompt="$2"
  local current_value="${!var_name:-}"
  if [ -z "$current_value" ]; then
    read -r -p "$prompt: " current_value
    printf -v "$var_name" '%s' "$current_value"
  fi
}

generate_secret() {
  if [ -z "$CONNECTOR_SECRET" ]; then
    if command -v openssl >/dev/null 2>&1; then
      CONNECTOR_SECRET="$(openssl rand -hex 32)"
    else
      CONNECTOR_SECRET="$(date +%s | sha256sum | awk '{print $1}')"
    fi
  fi
}

detect_public_url() {
  if [ -n "$MCP_PUBLIC_URL" ]; then
    return
  fi
  local public_ip
  public_ip="$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null || true)"
  if [ -n "$public_ip" ]; then
    MCP_PUBLIC_URL="https://${public_ip}"
  else
    MCP_PUBLIC_URL="https://127.0.0.1"
  fi
}

generate_tls_cert() {
  local cert_dir="$REPO_DIR/deploy/certs"
  local cert_file="$cert_dir/tls.crt"
  local key_file="$cert_dir/tls.key"
  if [ -f "$cert_file" ] && [ -f "$key_file" ]; then
    return
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "OpenSSL is required to generate the direct HTTPS certificate." >&2
    exit 1
  fi
  mkdir -p "$cert_dir"
  chmod 700 "$cert_dir"
  local host_name
  host_name="${MCP_PUBLIC_URL#https://}"
  host_name="${host_name#http://}"
  host_name="${host_name%%/*}"
  local san
  if [[ "$host_name" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    san="IP:${host_name}"
  else
    san="DNS:${host_name}"
  fi
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$key_file" \
    -out "$cert_file" \
    -days 365 \
    -subj "/CN=${host_name}" \
    -addext "subjectAltName=${san}" >/dev/null 2>&1
  chmod 600 "$key_file"
  chmod 644 "$cert_file"
}

clone_or_update_repo() {
  if [ "$SKIP_GIT_CLONE" = "1" ]; then
    return
  fi
  need_cmd git
  if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" pull --ff-only
  else
    git clone "$REPO_URL" "$REPO_DIR"
  fi
}

copy_addon() {
  local source_dir="$REPO_DIR/odoo_addons/odoo_mcp_connector"
  local target_dir="$ODOO_ADDONS_DIR/odoo_mcp_connector"
  if [ ! -d "$source_dir" ]; then
    echo "Missing add-on source: $source_dir" >&2
    exit 1
  fi
  sudo mkdir -p "$ODOO_ADDONS_DIR"
  sudo rm -rf "$target_dir"
  sudo cp -R "$source_dir" "$target_dir"
  if id odoo >/dev/null 2>&1; then
    sudo chown -R odoo:odoo "$target_dir"
  fi
}

ensure_addons_path() {
  if [ "$SKIP_ODOO_CONFIG_EDIT" = "1" ]; then
    return
  fi
  if [ ! -f "$ODOO_CONFIG" ]; then
    echo "Odoo config not found at $ODOO_CONFIG; skipping addons_path edit."
    return
  fi
  if grep -q "$ODOO_ADDONS_DIR" "$ODOO_CONFIG"; then
    return
  fi
  sudo cp "$ODOO_CONFIG" "$ODOO_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
  if grep -q '^addons_path[[:space:]]*=' "$ODOO_CONFIG"; then
    sudo sed -i "s#^addons_path[[:space:]]*=.*#&,${ODOO_ADDONS_DIR}#" "$ODOO_CONFIG"
  else
    printf '\naddons_path = %s\n' "$ODOO_ADDONS_DIR" | sudo tee -a "$ODOO_CONFIG" >/dev/null
  fi
}

restart_odoo() {
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q "^${ODOO_SERVICE}.service"; then
    sudo systemctl restart "$ODOO_SERVICE"
  else
    echo "Could not restart service '$ODOO_SERVICE'. Restart Odoo manually."
  fi
}

write_env() {
  mkdir -p "$REPO_DIR/deploy/audit"
  umask 077
  cat > "$REPO_DIR/deploy/.env" <<EOF
ODOO_URL=$ODOO_URL
ODOO_MCP_CONNECTOR_SECRET=$CONNECTOR_SECRET
ODOO_MCP_IDENTITY_ISSUER=$IDENTITY_ISSUER
ODOO_MCP_IDENTITY_AUDIENCE=$IDENTITY_AUDIENCE
ODOO_MCP_IDENTITY_JWKS_URL=$IDENTITY_JWKS_URL
ODOO_MCP_AUDIT_LOG=/var/log/odoo-mcp/audit.jsonl
ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8443
ODOO_MCP_BIND=$MCP_BIND
ODOO_MCP_PUBLIC_URL=$MCP_PUBLIC_URL
ODOO_MCP_TLS_CERT_FILE=$MCP_TLS_CERT_FILE
ODOO_MCP_TLS_KEY_FILE=$MCP_TLS_KEY_FILE
EOF
}

start_docker() {
  if [ "$SKIP_DOCKER_START" = "1" ]; then
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    (cd "$REPO_DIR/deploy" && docker compose up -d --build)
  else
    echo "Docker not found. Install Docker or run the MCP server manually."
  fi
}

print_next_steps() {
  cat <<EOF

Install complete.

Next steps in Odoo:
  1. Apps -> Update Apps List
  2. Install: Odoo MCP Connector
  3. Developer mode -> Settings -> Technical -> Parameters -> System Parameters
  4. Create or update:
       odoo_mcp_connector.signing_secret = $CONNECTOR_SECRET

Then validate:
  cd $REPO_DIR/deploy
  docker compose logs -f odoo-mcp

MCP service URL:
  $MCP_PUBLIC_URL

Direct exposure:
  Docker is configured to bind HTTPS MCP on ${MCP_BIND}:443.
  If external curl still fails, open TCP 443 in the server firewall and cloud security list.

TLS:
  A self-signed certificate was generated in deploy/certs.
  Test it with: curl -k $MCP_PUBLIC_URL

Important:
  Keep deploy/.env private. It contains the connector signing secret.
EOF
}

main() {
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
    exit 0
  fi

  prompt_if_empty ODOO_URL "Odoo URL, e.g. https://odoo.example.com"
  select_identity_defaults
  prompt_if_empty IDENTITY_ISSUER "OIDC issuer URL"
  prompt_if_empty IDENTITY_JWKS_URL "OIDC JWKS URL"
  prompt_if_empty IDENTITY_AUDIENCE "OIDC audience / OAuth Client ID"
  detect_public_url
  prompt_if_empty MCP_PUBLIC_URL "Public MCP URL, e.g. https://mcp.example.com"
  generate_secret

  clone_or_update_repo
  copy_addon
  ensure_addons_path
  restart_odoo
  generate_tls_cert
  write_env
  start_docker
  print_next_steps
}

main "$@"
