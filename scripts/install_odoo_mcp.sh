#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# scripts/install_odoo_mcp.sh — one-command installer for Giggso Odoo MCP
#
# Summary:
#   Clones/updates the repo, installs the Odoo addon, writes deploy/.env,
#   and starts Docker containers. Supports two frontend modes:
#     direct — uvicorn binds 0.0.0.0:8443 with TLS cert (Cycle 1 style)
#     nginx  — uvicorn plain HTTP, nginx sidecar terminates public TLS
#              on host port MCP_NGINX_HOST_PORT (default 9443)
#   Non-interactive when IDENTITY_ISSUER / IDENTITY_AUDIENCE /
#   IDENTITY_JWKS_URL are all pre-set (even to empty string).
#   CONNECTOR_SECRET is preserved from env if already set and non-empty.
#
# Usage (nginx sidecar mode, port 9443 — as deployed tonight):
#   sudo MCP_FRONTEND_MODE=nginx \
#        MCP_PUBLIC_URL=https://odoo.giggso.com:9443/mcp \
#        ODOO_URL=https://odoo.giggso.com \
#        ODOO_DB_NAME=odoo-prod \
#        IDENTITY_ISSUER=https://accounts.google.com \
#        IDENTITY_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs \
#        bash scripts/install_odoo_mcp.sh
#
# Version: 1.1.0 (Cycle 2.3 overnight cleanup — bugs 1-6 fixed)
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────
REPO_URL="https://github.com/giggsoinc/giggso-odoo.git"
REPO_DIR="${REPO_DIR:-$HOME/giggso-odoo}"
ODOO_ADDONS_DIR="${ODOO_ADDONS_DIR:-/opt/odoo/custom_addons}"
ODOO_CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
ODOO_URL="${ODOO_URL:-}"
ODOO_DB_NAME="${ODOO_DB_NAME:-}"
MCP_BIND="${MCP_BIND:-0.0.0.0}"
MCP_PUBLIC_URL="${MCP_PUBLIC_URL:-}"
MCP_TLS_CERT_FILE="${MCP_TLS_CERT_FILE:-/run/odoo-mcp/certs/tls.crt}"
MCP_TLS_KEY_FILE="${MCP_TLS_KEY_FILE:-/run/odoo-mcp/certs/tls.key}"
MCP_TLS_SOURCE_CERT_FILE="${MCP_TLS_SOURCE_CERT_FILE:-/home/opc/gg-odoo-app/domaincert/nginx.crt}"
MCP_TLS_SOURCE_KEY_FILE="${MCP_TLS_SOURCE_KEY_FILE:-/home/opc/gg-odoo-app/domaincert/nginx.key}"
MCP_RUN_UID="${MCP_RUN_UID:-$(id -u)}"
MCP_RUN_GID="${MCP_RUN_GID:-$(id -g)}"
IDENTITY_ISSUER="${IDENTITY_ISSUER:-}"
IDENTITY_AUDIENCE="${IDENTITY_AUDIENCE:-odoo-mcp}"
IDENTITY_JWKS_URL="${IDENTITY_JWKS_URL:-}"
CONNECTOR_SECRET="${CONNECTOR_SECRET:-}"
SKIP_GIT_CLONE="${SKIP_GIT_CLONE:-0}"
SKIP_ODOO_CONFIG_EDIT="${SKIP_ODOO_CONFIG_EDIT:-0}"
SKIP_DOCKER_START="${SKIP_DOCKER_START:-0}"
MCP_FRONTEND_MODE="${MCP_FRONTEND_MODE:-direct}"

# ── Helper modules ────────────────────────────────────────────────────
# shellcheck source=scripts/lib/identity-prompts.sh
source "$SCRIPT_DIR/lib/identity-prompts.sh"
# shellcheck source=scripts/lib/secret-mgmt.sh
source "$SCRIPT_DIR/lib/secret-mgmt.sh"
# shellcheck source=scripts/lib/direct-mode.sh
source "$SCRIPT_DIR/lib/direct-mode.sh"

# ── Utilities ─────────────────────────────────────────────────────────
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1" >&2; exit 1; }; }
prompt_if_empty() {
  local val="${!1:-}"; [ -n "$val" ] && return
  read -r -p "$2: " val; printf -v "$1" '%s' "$val"
}
detect_public_url() {
  [ -n "$MCP_PUBLIC_URL" ] && return
  local h public_ip
  if [ -n "$ODOO_URL" ]; then
    h="${ODOO_URL#*://}"; h="${h%%/*}"; h="${h%%:*}"
    MCP_PUBLIC_URL="https://${h}:8443"; return
  fi
  public_ip="$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null || true)"
  MCP_PUBLIC_URL="https://${public_ip:-127.0.0.1}:8443"
}

# ── Odoo addon ────────────────────────────────────────────────────────
clone_or_update_repo() {
  [ "$SKIP_GIT_CLONE" = "1" ] && return; need_cmd git
  if [ -d "$REPO_DIR/.git" ]; then git -C "$REPO_DIR" pull --ff-only
  else git clone "$REPO_URL" "$REPO_DIR"; fi
}
copy_addon() {
  local src="$REPO_DIR/odoo_addons/odoo_mcp_connector"
  local dst="$ODOO_ADDONS_DIR/odoo_mcp_connector"
  [ -d "$src" ] || { echo "Missing addon: $src" >&2; exit 1; }
  sudo mkdir -p "$ODOO_ADDONS_DIR"; sudo rm -rf "$dst"; sudo cp -R "$src" "$dst"
  id odoo >/dev/null 2>&1 && sudo chown -R odoo:odoo "$dst"
}
ensure_addons_path() {
  [ "$SKIP_ODOO_CONFIG_EDIT" = "1" ] && return
  [ -f "$ODOO_CONFIG" ] || { echo "Odoo config not found; skipping."; return; }
  grep -q "$ODOO_ADDONS_DIR" "$ODOO_CONFIG" && return
  sudo cp "$ODOO_CONFIG" "$ODOO_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
  if grep -q '^addons_path[[:space:]]*=' "$ODOO_CONFIG"; then
    sudo sed -i "s#^addons_path[[:space:]]*=.*#&,${ODOO_ADDONS_DIR}#" "$ODOO_CONFIG"
  else
    printf '\naddons_path = %s\n' "$ODOO_ADDONS_DIR" | sudo tee -a "$ODOO_CONFIG" >/dev/null
  fi
}
restart_odoo() {
  if command -v systemctl >/dev/null 2>&1 \
     && systemctl list-unit-files 2>/dev/null | grep -q "^${ODOO_SERVICE}.service"; then
    sudo systemctl restart "$ODOO_SERVICE"
  else echo "Could not restart '$ODOO_SERVICE'. Restart Odoo manually."; fi
}

# ── Next-steps banner — Bug 6: no hardcoded :8443 ────────────────────
print_next_steps() {
  cat <<EOF

Install complete.

Next steps in Odoo:
  1. Apps -> Update Apps List
  2. Install: Odoo MCP Connector
  3. Settings -> Technical -> Parameters -> System Parameters
  4. Set: odoo_mcp_connector.signing_secret = $CONNECTOR_SECRET
     $(secret_source_label)

MCP service URL: $MCP_PUBLIC_URL
Claude Desktop setup: docs/clients/claude-desktop.md
Logs: cd $REPO_DIR/deploy && docker compose logs -f odoo-mcp

Keep deploy/.env private — it contains the signing secret.
EOF
}

# ── main ──────────────────────────────────────────────────────────────
main() {
  [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ] && { head -30 "$0"; exit 0; }

  prompt_if_empty ODOO_URL "Odoo URL, e.g. https://odoo.example.com"
  [ -z "$ODOO_DB_NAME" ] && read -r -p "Odoo DB name (optional for Google SSO): " ODOO_DB_NAME

  # Bug 4: skips menu when any IDENTITY_* var is defined (see lib/identity-prompts.sh)
  select_identity_defaults
  prompt_if_empty IDENTITY_ISSUER "OIDC issuer URL"
  prompt_if_empty IDENTITY_JWKS_URL "OIDC JWKS URL"
  prompt_if_empty IDENTITY_AUDIENCE "OIDC audience"
  detect_public_url
  prompt_if_empty MCP_PUBLIC_URL "Public MCP URL"

  # Bug 5: preserves existing CONNECTOR_SECRET (see lib/secret-mgmt.sh)
  generate_secret

  clone_or_update_repo
  copy_addon
  ensure_addons_path
  restart_odoo

  # nginx mode: sidecar terminates TLS, uvicorn speaks plain HTTP.
  # direct mode: uvicorn serves HTTPS with its own cert.
  if [ "$MCP_FRONTEND_MODE" = "nginx" ]; then
    # shellcheck source=scripts/install_nginx_frontend.sh
    source "$SCRIPT_DIR/install_nginx_frontend.sh"
    apply_nginx_frontend
  else
    generate_tls_cert
    write_env
    start_docker
  fi

  print_next_steps
}

main "$@"
