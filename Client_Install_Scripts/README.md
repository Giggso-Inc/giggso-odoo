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
  - A note that the script needs **Node.js** (LTS) installed once — link them to https://nodejs.org
  - A note that the generated setup is valid for **90 days** — they re-run the script when it expires

---

## For the Client / End User (do this on your own laptop)

### Step 1 — Install Node.js (one-time, ~2 minutes)

- Open https://nodejs.org
- Click the green **LTS** button (left button) to download the installer
- Run the installer → Next → Next → Install → Finish
- Done — you never have to touch Node again

### Step 2 — Generate an Odoo API key (one-time)

- Open https://odoo.giggso.com in your browser
- Sign in with your Giggso email + password
- Click your avatar (top right) → **My Profile**
- Open the **Account Security** tab
- Click **New API Key**
- Name it `Claude Desktop`
- **Copy the 40-character key now** — Odoo only shows it once

### Step 3 — Run the script IT sent you

**Windows:**

- Save `Get-OdooMcpToken.ps1` to your Desktop
- Right-click the file → **Run with PowerShell**
- If Windows blocks it: open PowerShell as admin once and run:
  - `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux:**

- Save `get-odoo-mcp-token.sh` to your Desktop
- Open Terminal in that folder
- Run: `chmod +x get-odoo-mcp-token.sh && ./get-odoo-mcp-token.sh`

### Step 4 — Enter your credentials when prompted

- Email: your Giggso email (e.g. `you@giggso.com`)
- API key: the 40-character key you copied in Step 2

The script will:

- Check Node.js is installed
- Talk to the MCP server
- Mint a 90-day bearer token
- Build the full Claude Desktop command (with token baked in)
- **Copy that command to your clipboard**
- Tell you "SUCCESS"

### Step 5 — Add the connector in Claude Desktop

- Open Claude Desktop
- Go to **Settings → Developer → Edit Config** (or **Add MCP Server**)
- Choose **command / local server** (NOT remote URL)
- Name it: `giggso-odoo`
- Paste the command into the **Command** field (Ctrl+V on Windows, Cmd+V on Mac)
- Save → restart Claude Desktop
- The connector should now show up in your conversations

### Step 6 — Test it

- In Claude Desktop, start a new chat
- Type: `What MCP tools do you have for Odoo?`
- You should see tools like `crm_search_opportunities`, `crm_create_lead`, etc.

---

## Troubleshooting

- **Node.js is required** error → finish Step 1, close the terminal, re-run the script
- **401 Unauthorized** → email or API key wrong; redo Step 2, re-copy the key carefully
- **Cannot connect** → are you on VPN? Open https://odoo.giggso.com in a browser to confirm
- **PowerShell won't run** → see the Windows note in Step 3
- **Claude shows "Failed to connect"** → quit Claude completely (right-click tray icon → Quit), then re-open
- **Anything else** → email IT with the full error message
