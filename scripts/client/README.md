# Giggso Odoo MCP — Client Setup Scripts

For Giggso internal team members connecting Claude Desktop to the Odoo MCP server.

## Prereq (one-time, in Odoo)

1. Sign in to https://odoo.giggso.com
2. Top right → click your avatar → **My Profile**
3. **Account Security** tab → **New API Key**
4. Name it `Claude Desktop` → copy the 40-character key (you only see it once)

## Run the script for your OS

| OS                     | Script                       | How to run                                              |
| ---------------------- | ---------------------------- | ------------------------------------------------------- |
| Windows 10 / 11        | `Get-OdooMcpToken.ps1`       | Right-click → **Run with PowerShell**                   |
| macOS                  | `get-odoo-mcp-token.sh`      | `chmod +x get-odoo-mcp-token.sh && ./get-odoo-mcp-token.sh` |
| Linux                  | `get-odoo-mcp-token.sh`      | Same as macOS (needs `xclip` or `wl-copy` for clipboard) |

The script will:

1. Ask for your Odoo email + the API key you just copied
2. Mint a 90-day bearer token from the MCP server
3. Copy the token to your clipboard

## Next — wire into Claude Desktop

(Coming next — pending Claude Desktop UI walkthrough for custom-bearer connectors.)

## Troubleshooting

- **401 Unauthorized** — wrong email or API key. Re-copy the key from Odoo.
- **Cannot connect** — VPN issue. Open https://odoo.giggso.com in a browser to confirm reachability.
- **PowerShell blocked** on Windows — open PowerShell as admin and run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Token expiry

Tokens last 90 days. Re-run the script when it expires. Future Cycle 3 will replace this with Google SSO.
