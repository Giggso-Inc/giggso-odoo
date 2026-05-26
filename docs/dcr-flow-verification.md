# DCR Flow Verification — Cycle 2

End-to-end curl verification of the OAuth 2.1 + Dynamic Client Registration
flow for the Odoo MCP server. Run these commands against the live server after
deploying Cycle 2.

---

## Check 1 — Discovery metadata includes `registration_endpoint`

```bash
curl -s https://odoo.giggso.com:9443/mcp/.well-known/oauth-authorization-server | python3 -m json.tool
```

Expected: the JSON body includes:

```json
{
  "issuer": "https://odoo.giggso.com:9443/mcp",
  "authorization_endpoint": "https://odoo.giggso.com:9443/mcp/authorize",
  "token_endpoint": "https://odoo.giggso.com:9443/mcp/token",
  "registration_endpoint": "https://odoo.giggso.com:9443/mcp/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["none"],
  ...
}
```

---

## Check 2 — Dynamic Client Registration returns a `client_id`

```bash
curl -s -X POST https://odoo.giggso.com:9443/mcp/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"test","redirect_uris":["http://localhost:33418/callback"]}' \
  | python3 -m json.tool
```

Expected HTTP 201 with body like:

```json
{
  "client_id": "<random>",
  "client_name": "test",
  "redirect_uris": ["http://localhost:33418/callback"],
  "client_id_issued_at": 1234567890,
  "token_endpoint_auth_method": "none",
  "grant_types": ["authorization_code"],
  "response_types": ["code"]
}
```

---

## Check 3 — Full curl-based OAuth flow simulation

This simulates exactly what Claude Desktop does automatically.

### Step 1 — Register the test client and capture `client_id`

```bash
REG=$(curl -s -X POST https://odoo.giggso.com:9443/mcp/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"curl-test","redirect_uris":["http://localhost:9999/callback"]}')
echo "$REG" | python3 -m json.tool
CLIENT_ID=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_id'])")
echo "CLIENT_ID=$CLIENT_ID"
```

### Step 2 — Generate PKCE verifier + challenge

```bash
CODE_VERIFIER=$(python3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode())")
CODE_CHALLENGE=$(python3 -c "import sys,hashlib,base64; v=sys.argv[1].encode(); print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode())" "$CODE_VERIFIER")
STATE=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
echo "CODE_VERIFIER=$CODE_VERIFIER"
echo "CODE_CHALLENGE=$CODE_CHALLENGE"
echo "STATE=$STATE"
```

### Step 3 — Hit /authorize to create a flow (extract `flow_id` from HTML)

```bash
AUTH_RESP=$(curl -s "https://odoo.giggso.com:9443/mcp/authorize?\
response_type=code\
&client_id=${CLIENT_ID}\
&redirect_uri=http://localhost:9999/callback\
&code_challenge=${CODE_CHALLENGE}\
&code_challenge_method=S256\
&state=${STATE}")
# flow_id is embedded in the page's <a href> for the Odoo sign-in link
FLOW_ID=$(echo "$AUTH_RESP" | grep -oP '(?<=flow=)[^"&]+' | head -1)
echo "FLOW_ID=$FLOW_ID"
```

### Step 4 — Submit Odoo credentials (triggers 302 redirect with code)

Replace `your@email.com` and `your-api-key` with real Odoo credentials.

```bash
curl -s -D - -o /dev/null \
  -X POST https://odoo.giggso.com:9443/mcp/authorize/odoo \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "login=ravi@giggso.com" \
  --data-urlencode "password=YOUR_ODOO_API_KEY" \
  --data-urlencode "db=gg-odoo-db" \
  --data-urlencode "flow=${FLOW_ID}"
# Expected: HTTP/2 302  Location: http://localhost:9999/callback?code=<CODE>&state=<STATE>
```

Extract the code from the Location header:

```bash
LOCATION=$(curl -s -D - -o /dev/null \
  -X POST https://odoo.giggso.com:9443/mcp/authorize/odoo \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "login=ravi@giggso.com" \
  --data-urlencode "password=YOUR_ODOO_API_KEY" \
  --data-urlencode "db=gg-odoo-db" \
  --data-urlencode "flow=${FLOW_ID}" \
  | grep -i "^location:" | tr -d '\r')
echo "$LOCATION"
AUTH_CODE=$(echo "$LOCATION" | grep -oP '(?<=code=)[^&]+')
echo "AUTH_CODE=$AUTH_CODE"
```

### Step 5 — Exchange code for access token

```bash
TOKEN_RESP=$(curl -s -X POST https://odoo.giggso.com:9443/mcp/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=${AUTH_CODE}" \
  --data-urlencode "redirect_uri=http://localhost:9999/callback" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "code_verifier=${CODE_VERIFIER}")
echo "$TOKEN_RESP" | python3 -m json.tool
ACCESS_TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "ACCESS_TOKEN=$ACCESS_TOKEN"
```

### Step 6 — Use the token on /sse (or /auth/whoami)

```bash
curl -s https://odoo.giggso.com:9443/mcp/auth/whoami \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
# Expected: {"email":"ravi@giggso.com","subject":"odoo:<uid>","scopes":["crm","project"]}
```

---

## Check 4 — Claude Desktop click-through (manual)

1. Open Claude Desktop (Mac or Windows)
2. Go to **Settings → Integrations** (or **Add Custom Connector**)
3. Enter: `https://odoo.giggso.com:9443/mcp`
4. Click **Connect** — browser opens to the MCP landing page
5. Click **Sign in with Odoo**
6. Enter `ravi@giggso.com` and your Odoo API key in the Password field
7. Click **Authorize**
8. Browser shows "Authorized" and Claude Desktop shows **Connected**
9. In Claude, type: `use the whoami tool` → response should include `ravi@giggso.com`

---

## Redirect URI policy

The `/register` endpoint accepts:

- `http://localhost:<any-port>/...` — standard OAuth 2.1 loopback redirect
- `http://127.0.0.1:<any-port>/...` — same, numeric form
- `claude-desktop://<any-path>` — Claude Desktop's custom URI scheme

All other schemes (e.g. `https://attacker.com`) are rejected with
`400 invalid_redirect_uri`. This prevents the server from acting as an
open redirector.
