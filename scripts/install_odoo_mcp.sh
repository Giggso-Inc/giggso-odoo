#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/giggsoinc/giggso-odoo.git"
REPO_DIR="${REPO_DIR:-$HOME/giggso-odoo}"
ODOO_ADDONS_DIR="${ODOO_ADDONS_DIR:-/opt/odoo/custom_addons}"
ODOO_CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
ODOO_URL="${ODOO_URL:-}"
MCP_PUBLIC_URL="${MCP_PUBLIC_URL:-http://127.0.0.1:8088}"
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
  IDENTITY_AUDIENCE=odoo-mcp
  CONNECTOR_SECRET=<existing-secret>
  SKIP_GIT_CLONE=1
  SKIP_ODOO_CONFIG_EDIT=1
  SKIP_DOCKER_START=1
USAGE
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
ODOO_MCP_PORT=8088
ODOO_MCP_PUBLIC_URL=$MCP_PUBLIC_URL
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
  prompt_if_empty IDENTITY_ISSUER "OIDC issuer URL"
  prompt_if_empty IDENTITY_JWKS_URL "OIDC JWKS URL"
  prompt_if_empty MCP_PUBLIC_URL "Public MCP URL, e.g. https://mcp.example.com"
  generate_secret

  clone_or_update_repo
  copy_addon
  ensure_addons_path
  restart_odoo
  write_env
  start_docker
  print_next_steps
}

main "$@"
