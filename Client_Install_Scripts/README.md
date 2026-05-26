# Claude Desktop ↔ Giggso Odoo MCP — Setup

This folder lets a Giggso team member connect Claude Desktop to our Odoo CRM and Projects through the MCP server.

---

## For the Admin / IT (do this first, per user)

- Create an Odoo user for the person if they don't have one yet
- Confirm the user can sign in at https://odoo.giggso.com
- Email the person:
  - The script file matching their OS:
    - Windows → `Get-OdooMcpToken.ps1`
    - macOS / Linux → `get-odoo-mcp-token.sh`
  - A link to this README
  - A note that the token they generate is valid for **90 days** — they re-run the script when it expires
- Tell them to follow the **Client** section below

---

## For the Client / End User (do this on your own laptop)

### Step 1 — Generate an Odoo API key (one-time)

- Open https://odoo.giggso.com in your browser
- Sign in with your Giggso email + password
- Click your avatar (top right) → **My Profile**
- Open the **Account Security** tab
- Click **New API Key**
- Name it `Claude Desktop`
- **Copy the 40-character key now** — Odoo only shows it once

### Step 2 — Run the script IT sent you

**Windows:**

- Save `Get-OdooMcpToken.ps1` to your Desktop
- Right-click the file → **Run with PowerShell**
- If Windows blocks it: open PowerShell as admin once and run:
  - `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux:**

- Save `get-odoo-mcp-token.sh` to your Desktop
- Open Terminal in that folder
- Run: `chmod +x get-odoo-mcp-token.sh && ./get-odoo-mcp-token.sh`

### Step 3 — Enter your credentials when prompted

- Email: your Giggso email (e.g. `you@giggso.com`)
- API key: the 40-character key you copied in Step 1

The script will:

- Talk to the MCP server
- Mint a 90-day bearer token
- Copy the token to your clipboard
- Tell you "SUCCESS"

### Step 4 — Add the connector in Claude Desktop

*(Coming next — IT will email you exact UI steps once the Claude Desktop walkthrough is finalised.)*

---

## Troubleshooting

- **401 Unauthorized** → email or API key wrong; redo Step 1, re-copy the key carefully
- **Cannot connect** → are you on VPN? Open https://odoo.giggso.com in a browser to confirm
- **PowerShell won't run** → see the Windows note in Step 2
- **Anything else** → email IT with the full error message
