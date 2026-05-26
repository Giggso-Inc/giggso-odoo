# Get-OdooMcpToken.ps1
#
# Summary:
#   One-stop Claude Desktop setup for Giggso Odoo MCP (Windows).
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
#   Right-click the file -> Run with PowerShell
#
# Prereqs:
#   - Node.js installed (https://nodejs.org -- LTS installer is fine)
#   - An Odoo API key (Odoo -> Profile -> Account Security -> New API Key)
#
# Version: 0.2.0
# Execution context: Windows PowerShell 5.1+ or PowerShell 7+

$McpHost   = "https://odoo.giggso.com:9443"
$McpSseUrl = "$McpHost/mcp/sse"
$Database  = "gg-odoo-db"

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "  Giggso Odoo MCP - Claude Desktop Setup" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Node check ──────────────────────────────────────────────────
# mcp-remote is an npm package run via npx; without Node nothing works.
# Better to fail here with a clear message than to hand the user a command
# that errors inside Claude Desktop.
$nodeVersion = $null
try {
    $nodeVersion = (node --version) 2>$null
} catch { }

if (-not $nodeVersion) {
    Write-Host "Node.js is required but not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install it once:" -ForegroundColor Yellow
    Write-Host "  1. Open https://nodejs.org"
    Write-Host "  2. Download the LTS installer (left button)"
    Write-Host "  3. Run the installer (Next -> Next -> Install)"
    Write-Host "  4. Close PowerShell and re-run this script"
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "Node.js detected: $nodeVersion" -ForegroundColor Green
Write-Host ""

# ── Step 2: Credentials ─────────────────────────────────────────────────
$email  = Read-Host "Your Odoo email (e.g. you@giggso.com)"
$apikey = Read-Host "Your Odoo API key (40 chars, from Account Security)"

if ([string]::IsNullOrWhiteSpace($email) -or [string]::IsNullOrWhiteSpace($apikey)) {
    Write-Host ""
    Write-Host "ERROR: email and API key are both required." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# ── Step 3: Mint token ──────────────────────────────────────────────────
# JSON body matches the /auth/issue-token contract in bearer.py.
$body = @{
    login    = $email
    password = $apikey
    db       = $Database
} | ConvertTo-Json

Write-Host ""
Write-Host "Requesting token from $McpHost ..." -ForegroundColor Yellow

try {
    $resp = Invoke-RestMethod `
        -Method Post `
        -Uri "$McpHost/mcp/auth/issue-token" `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 15

    $token = $resp.token
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Server returned no token field."
    }

    # ── Step 4: Build the mcp-remote command ────────────────────────────
    # Claude Desktop's remote-MCP UI has no bearer field, so we wrap the
    # SSE endpoint with mcp-remote (an official MCP shim that injects the
    # Authorization header on behalf of the client).
    $command = "npx -y mcp-remote $McpSseUrl --header `"Authorization:Bearer $token`""

    Set-Clipboard -Value $command

    Write-Host ""
    Write-Host "SUCCESS - command copied to clipboard." -ForegroundColor Green
    Write-Host ""
    Write-Host "Token preview: $($token.Substring(0,20))...$($token.Substring($token.Length-10))"
    Write-Host "Valid for:     90 days"
    Write-Host ""
    Write-Host "NEXT STEPS:" -ForegroundColor Cyan
    Write-Host "  1. Open Claude Desktop"
    Write-Host "  2. Settings -> Developer -> Edit Config (or Add MCP Server)"
    Write-Host "  3. Choose 'command' / local server (NOT remote URL)"
    Write-Host "  4. Paste the command into the Command field (Ctrl+V)"
    Write-Host "  5. Name it: giggso-odoo"
    Write-Host "  6. Save and restart Claude Desktop"
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "FAILED - $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - 401 Unauthorized: check email spelling and re-copy the API key"
    Write-Host "  - Cannot connect:   are you on VPN / can you open https://odoo.giggso.com in a browser?"
    Write-Host "  - Other:            email IT with this error message"
    Write-Host ""
}

Read-Host "Press Enter to close"
