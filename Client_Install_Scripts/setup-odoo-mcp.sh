#!/bin/bash
#
# setup-odoo-mcp.sh
#
# Summary:
#   One-stop Claude Desktop setup for any Odoo MCP Server deployment.
#   Parameterized — no hardcoded URLs, databases, or company names.
#   Works with OAuth 2.0 (DCR flow via mcp-remote) or legacy bearer token.
#
# Usage:
#   chmod +x setup-odoo-mcp.sh
#
#   # Interactive (prompts for everything):
#   ./setup-odoo-mcp.sh
#
#   # Non-interactive (all params via env or flags):
#   MCP_SERVER_URL=https://odoo-mcp.example.com \
#   MCP_SERVER_NAME=my-odoo \
#   ./setup-odoo-mcp.sh
#
# Parameters (env vars or interactive prompts):
#   MCP_SERVER_URL    Full HTTPS URL of the MCP server (required)
#   MCP_SERVER_NAME   Label shown in Claude Desktop (default: odoo-mcp)
#
# What it does:
#   1. Checks Node.js + npx are installed
#   2. Resolves MCP server URL (env, arg, or interactive prompt)
#   3. Builds the claude_desktop_config.json snippet
#   4. Offers to auto-patch the config file, or prints it for manual paste
#   5. Prints next steps
#
# Transport:  streamable-http  (OAuth 2.0 — mcp-remote handles login in browser)
# Prereqs:    Node.js >= 18  (https://nodejs.org)
# Version:    1.0.0

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'
RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

# ── Banner ───────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Odoo MCP Server — Claude Desktop Setup   ${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ── Step 1: Node check ───────────────────────────────────────────────────
if ! command -v node >/dev/null 2>&1; then
    echo -e "${RED}Node.js is required but not installed.${NC}"
    echo ""
    echo -e "${YELLOW}Install Node.js once:${NC}"
    if [[ "${OSTYPE:-}" == "darwin"* ]]; then
        echo "  brew install node   OR   https://nodejs.org (LTS installer)"
    else
        echo "  sudo apt install -y nodejs npm   (Ubuntu/Debian)"
        echo "  sudo dnf install -y nodejs       (Fedora/RHEL)"
        echo "  OR: https://nodejs.org (LTS installer)"
    fi
    echo ""
    echo "Then re-run this script."
    exit 1
fi
echo -e "${GREEN}Node.js $(node --version) detected.${NC}"

# ── Step 2: Resolve MCP server URL ───────────────────────────────────────
if [[ -z "${MCP_SERVER_URL:-}" ]]; then
    echo ""
    read -r -p "MCP Server URL (e.g. https://odoo-mcp.example.com): " MCP_SERVER_URL
fi

if [[ -z "${MCP_SERVER_URL:-}" ]]; then
    echo -e "${RED}ERROR: MCP_SERVER_URL is required.${NC}"
    exit 1
fi

# Strip trailing slash
MCP_SERVER_URL="${MCP_SERVER_URL%/}"

# ── Step 3: Server name (label in Claude Desktop) ────────────────────────
MCP_SERVER_NAME="${MCP_SERVER_NAME:-odoo-mcp}"

# ── Step 4: Verify server is reachable ───────────────────────────────────
echo ""
echo -e "${YELLOW}Checking server reachability...${NC}"
HTTP_STATUS=$(curl -sko /dev/null -w "%{http_code}" \
    --max-time 10 \
    "${MCP_SERVER_URL}/.well-known/oauth-authorization-server" 2>/dev/null || echo "000")

if [[ "$HTTP_STATUS" == "200" ]]; then
    echo -e "${GREEN}Server reachable — OAuth metadata found.${NC}"
    TRANSPORT="streamable-http"
elif [[ "$HTTP_STATUS" == "000" ]]; then
    echo -e "${RED}Cannot reach ${MCP_SERVER_URL}${NC}"
    echo "  Check URL, VPN, and that the server is running."
    exit 1
else
    echo -e "${YELLOW}Server reachable (HTTP ${HTTP_STATUS}) — may be SSE or custom setup.${NC}"
    TRANSPORT="streamable-http"
fi

# ── Step 5: Build config snippet ─────────────────────────────────────────
CONFIG_SNIPPET=$(cat <<SNIPPET
{
  "mcpServers": {
    "${MCP_SERVER_NAME}": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "${MCP_SERVER_URL}",
        "--transport",
        "${TRANSPORT}"
      ]
    }
  }
}
SNIPPET
)

# ── Step 6: Locate Claude Desktop config ─────────────────────────────────
if [[ "${OSTYPE:-}" == "darwin"* ]]; then
    CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
elif [[ "${OSTYPE:-}" == "linux"* ]]; then
    CLAUDE_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
else
    CLAUDE_CONFIG=""
fi

# ── Step 7: Auto-patch or print ──────────────────────────────────────────
echo ""
echo -e "${CYAN}Config snippet for Claude Desktop:${NC}"
echo "─────────────────────────────────────────────"
echo "$CONFIG_SNIPPET"
echo "─────────────────────────────────────────────"

if [[ -n "$CLAUDE_CONFIG" && -f "$CLAUDE_CONFIG" ]]; then
    echo ""
    echo -e "${YELLOW}Claude Desktop config found at:${NC}"
    echo "  $CLAUDE_CONFIG"
    echo ""
    read -r -p "Auto-add '${MCP_SERVER_NAME}' to your Claude Desktop config? [y/N] " AUTOPATCH
    if [[ "${AUTOPATCH,,}" == "y" ]]; then
        # Merge the new server into existing config using python3
        python3 - "$CLAUDE_CONFIG" "$MCP_SERVER_NAME" "$MCP_SERVER_URL" "$TRANSPORT" <<'PYEOF'
import json, sys
config_path, name, url, transport = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(config_path) as f:
    config = json.load(f)
config.setdefault("mcpServers", {})[name] = {
    "command": "npx",
    "args": ["-y", "mcp-remote", url, "--transport", transport]
}
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
print("Patched.")
PYEOF
        echo -e "${GREEN}Done — '${MCP_SERVER_NAME}' added to Claude Desktop config.${NC}"
    else
        echo "Skipped auto-patch. Copy the snippet above manually."
    fi
else
    echo ""
    echo -e "${YELLOW}Claude Desktop config not found at the default path.${NC}"
    echo "Copy the snippet above into your claude_desktop_config.json manually."
fi

# ── Step 8: Next steps ───────────────────────────────────────────────────
echo ""
echo -e "${CYAN}NEXT STEPS:${NC}"
echo "  1. Restart Claude Desktop"
echo "  2. Click the tools icon (hammer) — '${MCP_SERVER_NAME}' should appear"
echo "  3. A browser window will open for Odoo login (first time only)"
echo "  4. After login, Claude can access your Odoo data"
echo ""
echo -e "${GREEN}Setup complete.${NC}"
echo ""
