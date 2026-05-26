#!/bin/bash
#
# get-odoo-mcp-token.sh
#
# Summary:
#   Mints a 90-day Odoo MCP bearer token for Claude Desktop connector setup.
#   For Giggso internal team — Mac and Linux users.
#
# What it does:
#   1. Prompts for Odoo email + API key
#   2. POSTs to https://odoo.giggso.com:9443/mcp/auth/issue-token
#   3. Copies the JWT bearer token to the clipboard (pbcopy on Mac, xclip on Linux)
#   4. User pastes the token into Claude Desktop when adding the connector
#
# Usage:
#   chmod +x get-odoo-mcp-token.sh
#   ./get-odoo-mcp-token.sh
#
# Prereqs (one-time, done in Odoo web UI):
#   Odoo -> Profile (top right) -> My Profile -> Account Security tab
#       -> "New API Key" -> name it "Claude Desktop" -> copy the 40-char string
#
# Version: 0.1.0
# Execution context: bash on macOS or Linux (requires curl + python3)

set -e

# Hardcoded for the Giggso internal MCP deployment. Update if the host
# or database name ever changes — both values are environment-specific
# and don't belong in user input.
MCP_HOST="https://odoo.giggso.com:9443"
DATABASE="gg-odoo-db"

# ── Color helpers ───────────────────────────────────────────────────────
# Plain ANSI; works in Terminal.app, iTerm2, GNOME Terminal, VS Code.
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${CYAN}===========================================${NC}"
echo -e "${CYAN}  Giggso Odoo MCP — Claude Desktop Token${NC}"
echo -e "${CYAN}===========================================${NC}"
echo ""

# Read inputs interactively. -r prevents backslash interpretation so
# API keys with weird chars survive intact.
read -r -p "Your Odoo email (e.g. you@giggso.com): " EMAIL
read -r -p "Your Odoo API key (40 chars, from Account Security): " APIKEY

if [ -z "$EMAIL" ] || [ -z "$APIKEY" ]; then
    echo ""
    echo -e "${RED}ERROR: email and API key are both required.${NC}"
    exit 1
fi

# JSON body matches the /auth/issue-token contract in bearer.py.
# python3 -c is the most portable way to escape user input safely without
# pulling jq as a dependency.
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

# -k tolerates self-signed certs in case the cert is ever swapped during
# rotation; the prod cert is a public GoDaddy wildcard so this is belt+suspenders.
# -sS = silent except on error. -w writes the HTTP code on a separate line.
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
    echo -e "${RED}FAILED — HTTP $HTTP_STATUS${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "  - 401 Unauthorized: check email spelling and re-copy the API key"
    echo "  - 000 / cannot connect: VPN issue — can you open https://odoo.giggso.com in a browser?"
    echo "  - Other: email IT with this output"
    echo ""
    echo "Server response: $HTTP_BODY"
    exit 1
fi

# Extract token via python3 — same reason as above (portable, no jq).
TOKEN=$(echo "$HTTP_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('token',''))")

if [ -z "$TOKEN" ]; then
    echo -e "${RED}FAILED — server returned no token field.${NC}"
    echo "Server response: $HTTP_BODY"
    exit 1
fi

# Clipboard: Mac has pbcopy, most Linuxes need xclip or wl-copy.
# Fallback is just printing the token so user can copy manually.
if command -v pbcopy >/dev/null 2>&1; then
    echo -n "$TOKEN" | pbcopy
    CLIPBOARD_MSG="Token copied to clipboard."
elif command -v wl-copy >/dev/null 2>&1; then
    echo -n "$TOKEN" | wl-copy
    CLIPBOARD_MSG="Token copied to clipboard (Wayland)."
elif command -v xclip >/dev/null 2>&1; then
    echo -n "$TOKEN" | xclip -selection clipboard
    CLIPBOARD_MSG="Token copied to clipboard (X11)."
else
    CLIPBOARD_MSG="No clipboard tool found — copy the token below manually."
fi

echo ""
echo -e "${GREEN}SUCCESS — $CLIPBOARD_MSG${NC}"
echo ""
echo "Token preview: ${TOKEN:0:20}...${TOKEN: -10}"
echo "Valid for:     90 days"
echo ""
echo -e "${CYAN}NEXT STEPS:${NC}"
echo "  1. Open Claude Desktop"
echo "  2. Settings -> Connectors -> Add custom connector"
echo "  3. Follow the setup instructions emailed by IT"
echo "     (paste the token when prompted)"
echo ""

# Only print the full token if clipboard failed — keeps it out of
# scrollback history for normal users.
if [ "$CLIPBOARD_MSG" = "No clipboard tool found — copy the token below manually." ]; then
    echo "Full token:"
    echo "$TOKEN"
    echo ""
fi
