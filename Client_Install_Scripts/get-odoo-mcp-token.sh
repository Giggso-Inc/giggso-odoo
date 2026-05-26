#!/bin/bash
#
# get-odoo-mcp-token.sh
#
# Summary:
#   One-stop Claude Desktop setup for Giggso Odoo MCP (Mac/Linux).
#   Mints a 90-day bearer token AND builds the full mcp-remote command
#   the user pastes into Claude Desktop's custom MCP server "command" field.
#
# What it does:
#   1. Checks Node.js is installed (Claude Desktop's remote-MCP UI doesn't
#      accept bearer headers, so we wrap the server in `mcp-remote`)
#   2. Prompts for Odoo email + API key
#   3. POSTs to /mcp/auth/issue-token, gets a 90-day JWT
#   4. Builds the full npx mcp-remote command with the token baked in
#   5. Copies that COMMAND (not the raw token) to the clipboard
#   6. User pastes into Claude Desktop -> done
#
# Usage:
#   chmod +x get-odoo-mcp-token.sh
#   ./get-odoo-mcp-token.sh
#
# Prereqs:
#   - Node.js installed (https://nodejs.org -- LTS installer, or `brew install node`)
#   - An Odoo API key (Odoo -> Profile -> Account Security -> New API Key)
#
# Version: 0.2.0
# Execution context: bash on macOS or Linux (requires curl + python3 + node)

set -e

MCP_HOST="https://odoo.giggso.com:9443"
MCP_SSE_URL="$MCP_HOST/mcp/sse"
DATABASE="gg-odoo-db"

# ── Color helpers ───────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${CYAN}===========================================${NC}"
echo -e "${CYAN}  Giggso Odoo MCP - Claude Desktop Setup${NC}"
echo -e "${CYAN}===========================================${NC}"
echo ""

# ── Step 1: Node check ──────────────────────────────────────────────────
# mcp-remote is an npm package run via npx; without Node nothing works.
# Better to fail here with a clear message than to hand the user a command
# that errors inside Claude Desktop.
if ! command -v node >/dev/null 2>&1; then
    echo -e "${RED}Node.js is required but not installed.${NC}"
    echo ""
    echo -e "${YELLOW}Install it once:${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  Option 1: open https://nodejs.org and run the LTS installer"
        echo "  Option 2: in Terminal run -> brew install node"
    else
        echo "  Option 1: open https://nodejs.org and run the LTS installer"
        echo "  Option 2 (Ubuntu/Debian): sudo apt install -y nodejs npm"
        echo "  Option 3 (Fedora):        sudo dnf install -y nodejs"
    fi
    echo ""
    echo "Then close this terminal and re-run the script."
    exit 1
fi
echo -e "${GREEN}Node.js detected: $(node --version)${NC}"
echo ""

# ── Step 2: Credentials ─────────────────────────────────────────────────
read -r -p "Your Odoo email (e.g. you@giggso.com): " EMAIL
read -r -p "Your Odoo API key (40 chars, from Account Security): " APIKEY

if [ -z "$EMAIL" ] || [ -z "$APIKEY" ]; then
    echo ""
    echo -e "${RED}ERROR: email and API key are both required.${NC}"
    exit 1
fi

# ── Step 3: Mint token ──────────────────────────────────────────────────
# JSON body matches the /auth/issue-token contract in bearer.py.
# python3 -c is the most portable way to escape user input safely.
BODY=$(python3 -c "
import json, sys
print(json.dumps({
    'login': sys.argv[1],
    'password': sys.argv[2],
    'db': sys.argv[3],
}))
" "$EMAIL" "$APIKEY" "$DATABASE")

echo ""
echo -e "${YELLOW}Requesting token from ${MCP_HOST} ...${NC}"

HTTP_RESPONSE=$(curl -ksS \
    -X POST "$MCP_HOST/mcp/auth/issue-token" \
    -H "Content-Type: application/json" \
    -d "$BODY" \
    -w "\n__HTTP_STATUS__%{http_code}" \
    --max-time 15 || echo "__HTTP_STATUS__000")

HTTP_STATUS=$(echo "$HTTP_RESPONSE" | grep "__HTTP_STATUS__" | sed 's/__HTTP_STATUS__//')
HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '/__HTTP_STATUS__/d')

if [ "$HTTP_STATUS" != "200" ]; then
    echo ""
    echo -e "${RED}FAILED - HTTP $HTTP_STATUS${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "  - 401 Unauthorized: check email spelling and re-copy the API key"
    echo "  - 000 / cannot connect: VPN issue - can you open https://odoo.giggso.com in a browser?"
    echo "  - Other: email IT with this output"
    echo ""
    echo "Server response: $HTTP_BODY"
    exit 1
fi

TOKEN=$(echo "$HTTP_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('token',''))")

if [ -z "$TOKEN" ]; then
    echo -e "${RED}FAILED - server returned no token field.${NC}"
    echo "Server response: $HTTP_BODY"
    exit 1
fi

# ── Step 4: Build the mcp-remote command ────────────────────────────────
# Claude Desktop's remote-MCP UI has no bearer field, so we wrap the
# SSE endpoint with mcp-remote (an official MCP shim that injects the
# Authorization header on behalf of the client).
COMMAND="npx -y mcp-remote $MCP_SSE_URL --header \"Authorization:Bearer $TOKEN\""

# Clipboard: Mac has pbcopy, Linux varies (wl-copy or xclip).
if command -v pbcopy >/dev/null 2>&1; then
    echo -n "$COMMAND" | pbcopy
    CLIPBOARD_MSG="Command copied to clipboard."
elif command -v wl-copy >/dev/null 2>&1; then
    echo -n "$COMMAND" | wl-copy
    CLIPBOARD_MSG="Command copied to clipboard (Wayland)."
elif command -v xclip >/dev/null 2>&1; then
    echo -n "$COMMAND" | xclip -selection clipboard
    CLIPBOARD_MSG="Command copied to clipboard (X11)."
else
    CLIPBOARD_MSG="No clipboard tool found - copy the command below manually."
fi

echo ""
echo -e "${GREEN}SUCCESS - $CLIPBOARD_MSG${NC}"
echo ""
echo "Token preview: ${TOKEN:0:20}...${TOKEN: -10}"
echo "Valid for:     90 days"
echo ""
echo -e "${CYAN}NEXT STEPS:${NC}"
echo "  1. Open Claude Desktop"
echo "  2. Settings -> Developer -> Edit Config (or Add MCP Server)"
echo "  3. Choose 'command' / local server (NOT remote URL)"
echo "  4. Paste the command into the Command field (Cmd+V on Mac, Ctrl+V on Linux)"
echo "  5. Name it: giggso-odoo"
echo "  6. Save and restart Claude Desktop"
echo ""

if [ "$CLIPBOARD_MSG" = "No clipboard tool found - copy the command below manually." ]; then
    echo "Full command:"
    echo "$COMMAND"
    echo ""
fi
