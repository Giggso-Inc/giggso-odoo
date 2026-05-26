# Claude Desktop ↔ Giggso Odoo MCP — Setup

This folder lets a Giggso team member connect Claude Desktop to our Odoo CRM and Projects through the MCP server.

---

## Recommended: One-Click Browser Flow (Cycle 2+)

Claude Desktop now supports a native OAuth browser flow. **No Node.js, no scripts, no JSON editing.**

### Steps (Mac and Windows)

1. Open Claude Desktop
2. Go to **Settings → Integrations** → **Add Custom Connector**
3. Enter the server URL: `https://odoo.giggso.com:9443/mcp`
4. Click **Connect** — your browser opens automatically
5. Click **Sign in with Odoo**
6. Enter your Giggso email and your **Odoo API key** (see below)
7. Click **Authorize**
8. Claude Desktop shows **Connected**

That's it. No scripts, no terminal, no config files.

### Getting your Odoo API key

- Open https://odoo.giggso.com in your browser
- Sign in with your Giggso email + password
- Click your avatar (top right) → **My Profile**
- Open the **Account Security** tab
- Click **New API Key** → name it `Claude Desktop`
- **Copy the 40-character key immediately** — Odoo shows it only once

The key goes in the **Password** field of the Odoo sign-in form. Your Odoo
password itself will not work — Odoo 19 Enterprise requires API keys for
programmatic access.

### Re-authorizing

The session expires after 12 hours. Claude Desktop will prompt you to
re-authorize automatically. Just click through the browser flow again.

---

## Deprecated: Script-based setup (pre-Cycle 2)

> **These scripts are deprecated.** They still work but require Node.js and
> manual JSON editing. Use the browser flow above instead.
>
> Kept here only for legacy environments that cannot use the browser flow
> (e.g., headless CI systems or automated pipelines).

<details>
<summary>Old script instructions (click to expand)</summary>

### For the Admin / IT (do this first, per user)

- Create an Odoo user for the person if they don't have one yet
- Confirm the user can sign in at https://odoo.giggso.com
- Email the person:
  - The script file matching their OS:
    - Windows → `Get-OdooMcpToken.ps1`
    - macOS / Linux → `get-odoo-mcp-token.sh`
  - A link to this README
  - A note that the script needs **Node.js** (LTS) installed once — link them to https://nodejs.org
  - A note that the generated setup is valid for **90 days** — they re-run the script when it expires

### For the Client / End User (do this on your own laptop)

#### Step 1 — Install Node.js (one-time, ~2 minutes)

- Open https://nodejs.org
- Click the green **LTS** button (left button) to download the installer
- Run the installer → Next → Next → Install → Finish

#### Step 2 — Generate an Odoo API key (one-time)

- Open https://odoo.giggso.com in your browser
- Sign in with your Giggso email + password
- Click your avatar (top right) → **My Profile**
- Open the **Account Security** tab
- Click **New API Key**
- Name it `Claude Desktop`
- **Copy the 40-character key now** — Odoo only shows it once

#### Step 3 — Run the script IT sent you

**Windows:**
- Save `Get-OdooMcpToken.ps1` to your Desktop
- Right-click the file → **Run with PowerShell**
- If Windows blocks it: open PowerShell as admin once and run:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux:**
- Save `get-odoo-mcp-token.sh` to your Desktop
- Open Terminal in that folder
- Run: `chmod +x get-odoo-mcp-token.sh && ./get-odoo-mcp-token.sh`

#### Step 4 — Enter your credentials when prompted

- Email: your Giggso email (e.g. `you@giggso.com`)
- API key: the 40-character key you copied in Step 2

The script will check Node.js, talk to the MCP server, mint a 90-day bearer
token, build the full Claude Desktop command, copy it to your clipboard, and
print "SUCCESS".

#### Step 5 — Add the connector in Claude Desktop

- Open Claude Desktop → **Settings → Developer → Edit Config**
- Choose **command / local server** (NOT remote URL)
- Name it: `giggso-odoo`
- Paste the command into the **Command** field
- Save → restart Claude Desktop

</details>

---

## Troubleshooting (browser flow)

| Symptom | Fix |
|---|---|
| Browser does not open | Try pasting `https://odoo.giggso.com:9443/mcp/authorize` manually |
| "Invalid credentials" | Use your API key, not your Odoo password |
| "Unknown client_id" | Start the flow fresh from Claude Desktop (do not reuse old URLs) |
| "Flow expired" | The 10-minute auth window passed; start again from Claude Desktop |
| Claude shows "Failed" | Quit Claude completely, reopen, and try again |
| Anything else | Email IT with the full error message |
