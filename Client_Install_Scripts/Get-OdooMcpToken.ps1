# Get-OdooMcpToken.ps1
#
# Summary:
#   Mints a 90-day Odoo MCP bearer token for Claude Desktop connector setup.
#   For Giggso internal team — Windows users.
#
# What it does:
#   1. Prompts for Odoo email + API key
#   2. POSTs to https://odoo.giggso.com:9443/mcp/auth/issue-token
#   3. Copies the JWT bearer token to the clipboard
#   4. User pastes the token into Claude Desktop when adding the connector
#
# Usage:
#   Right-click the file -> Run with PowerShell
#   (or from terminal: powershell -ExecutionPolicy Bypass -File .\Get-OdooMcpToken.ps1)
#
# Prereqs (one-time, done in Odoo web UI):
#   Odoo -> Profile (top right) -> My Profile -> Account Security tab
#       -> "New API Key" -> name it "Claude Desktop" -> copy the 40-char string
#
# Version: 0.1.0
# Execution context: Windows PowerShell 5.1+ or PowerShell 7+

# Hardcoded for the Giggso internal MCP deployment. Update if the host
# or database name ever changes — both values are environment-specific
# and don't belong in user input.
$McpHost  = "https://odoo.giggso.com:9443"
$Database = "gg-odoo-db"

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "  Giggso Odoo MCP — Claude Desktop Token" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# Read-Host prompts inline; -AsSecureString would hide the key but then
# we can't put it on the clipboard without an extra conversion step.
# This script runs locally on the user's own laptop so plain prompt is fine.
$email  = Read-Host "Your Odoo email (e.g. you@giggso.com)"
$apikey = Read-Host "Your Odoo API key (40 chars, from Account Security)"

if ([string]::IsNullOrWhiteSpace($email) -or [string]::IsNullOrWhiteSpace($apikey)) {
    Write-Host ""
    Write-Host "ERROR: email and API key are both required." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

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

    # Set-Clipboard is built into PowerShell 5+; no module install needed.
    Set-Clipboard -Value $token

    Write-Host ""
    Write-Host "SUCCESS — token copied to clipboard." -ForegroundColor Green
    Write-Host ""
    Write-Host "Token preview: $($token.Substring(0,20))...$($token.Substring($token.Length-10))"
    Write-Host "Valid for:     90 days"
    Write-Host ""
    Write-Host "NEXT STEPS:" -ForegroundColor Cyan
    Write-Host "  1. Open Claude Desktop"
    Write-Host "  2. Settings -> Connectors -> Add custom connector"
    Write-Host "  3. Follow the setup instructions emailed by IT"
    Write-Host "     (paste the token when prompted — it's already in your clipboard)"
    Write-Host ""

} catch {
    # Friendly error messages mapped to the actual server responses.
    # 401 = wrong email/api-key. 5xx = server problem. Anything else =
    # network/DNS/firewall — most common in remote-worker setups.
    Write-Host ""
    Write-Host "FAILED — $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - 401 Unauthorized: check email spelling and re-copy the API key"
    Write-Host "  - Cannot connect:   are you on VPN / can you open https://odoo.giggso.com in a browser?"
    Write-Host "  - Other:            email IT with this error message"
    Write-Host ""
}

Read-Host "Press Enter to close"
