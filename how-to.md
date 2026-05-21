# How To Use Giggso Odoo MCP

This guide is the operational path for both administrators and end users.

## 1) Install the repo on the Odoo server

```bash
git clone https://github.com/giggsoinc/giggso-odoo.git
cd giggso-odoo
bash scripts/install_odoo_mcp.sh
```

The installer prepares `deploy/.env`, copies the Odoo connector, and starts the MCP service when Docker is available.

## 2) Install the Odoo add-on

Copy the connector into your Odoo custom addons path:

```bash
cp -R odoo_addons/odoo_mcp_connector /opt/odoo/custom_addons/
```

Then in Odoo:

1. Enable developer mode.
2. Go to `Apps`.
3. Click `Update Apps List`.
4. Search for `Odoo MCP Connector`.
5. Install it.

If the module does not appear, the custom addons path is wrong or the Odoo service has not been restarted.

## 3) Set the connector signing secret

In Odoo:

```text
Settings -> Technical -> Parameters -> System Parameters
```

Create:

```text
odoo_mcp_connector.signing_secret = <same value as ODOO_MCP_CONNECTOR_SECRET>
```

## 4) Choose the login mode

The landing page supports two paths:

- **Sign in with Odoo** for plain Odoo username/password environments
- **Sign in with Google** for Google Workspace / Google Cloud SSO, if configured

### Plain Odoo login

Use this when the company does not have SSO.

1. Open the MCP landing page:
   ```text
   https://odoo.giggso.com:8443/
   ```
2. Click `Sign in with Odoo`.
3. Enter:
   - database
   - login
   - password
4. The server creates a short-lived MCP session.

### Google SSO

Use this when the organization has Google identity and you want browser-based sign-in.

1. Set `ODOO_MCP_GOOGLE_CLIENT_ID`.
2. Register:
   ```text
   <ODOO_MCP_PUBLIC_URL>/oauth/callback
   ```
3. Open the landing page.
4. Click `Sign in with Google`.
5. Complete Google sign-in in the browser.

## 5) Connect Claude, Codex, or another MCP client

Use the MCP endpoint:

```text
https://odoo.giggso.com:8443/sse
```

What happens next depends on the client:

- Clients with browser OAuth support should follow the authorization link.
- Clients without that support may rely on the landing page session or bearer token flow.

## 6) Try low-risk prompts first

Health and access:

```text
Check whether I can access Odoo.
```

```text
List my available Odoo capabilities.
```

CRM:

```text
Search Odoo CRM opportunities for ACME.
```

```text
Add a note to lead 123: customer asked for pricing by Friday.
```

Project:

```text
List my Odoo projects.
```

```text
Move task 987 to stage 12.
```

## 7) What to expect from permissions

The assistant only sees what the mapped Odoo user can access.

If a record is hidden in Odoo, the MCP layer should not reveal it.

## 8) After a git pull on the server

Run:

```bash
cd ~/giggso-odoo
git pull
cd deploy
docker compose up -d --build --force-recreate
docker compose logs --tail=50 odoo-mcp
```

Then verify:

```bash
curl -k https://odoo.giggso.com:8443/
curl -k https://odoo.giggso.com:8443/.well-known/oauth-protected-resource
curl -k https://odoo.giggso.com:8443/.well-known/oauth-authorization-server
```

## 9) Troubleshooting

- If the landing page shows the wrong hostname, fix `ODOO_MCP_PUBLIC_URL` in `deploy/.env`.
- If the Google link appears unexpectedly, remove `ODOO_MCP_GOOGLE_CLIENT_ID`.
- If Claude says it cannot reach the server, verify the client is using the current `/sse` URL and that the server has been restarted after the latest pull.
- If the Odoo add-on does not show up, check the mounted addons path inside the running Odoo container.

## 10) Daily operator checklist

- Confirm the MCP container is running.
- Confirm the landing page resolves on the expected hostname.
- Confirm the Odoo add-on is installed.
- Confirm the signing secret matches on both sides.
- Confirm the identity provider settings are still valid.
