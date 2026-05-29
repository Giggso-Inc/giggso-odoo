# README — CRM Tools

Version: 1.0 · Last verified: 2026-05-29 · Surfaced through Claude.ai

Every CRM tool runs under **your Odoo identity** via the MCP
connector. You can only act on records your Odoo user already has
access to. Writes are audited.

> If you can't connect to the Odoo MCP yet, see **README-USER.md**.

---

## Available tools

| Tool | Reads/Writes | One-line purpose |
| --- | --- | --- |
| `crm_search_opportunities` | read | Find leads/opportunities by free text |
| `crm_list_stale_opportunities` | read | Opportunities with no planned next activity |
| `crm_list_stages` | read | Stage catalog (for `stage_id` references) |
| `crm_create_lead` | write | Create a new lead |
| `crm_add_note` | write | Post a chatter note on a lead |
| `crm_update_stage` | write | Move a lead to a different stage |

Returned fields on opportunities:
`id, name, partner_id, contact_name, email_from, phone, stage_id,
user_id, team_id, probability, expected_revenue, date_deadline,
activity_state`.

---

## `crm_search_opportunities`

**Purpose:** find CRM leads / opportunities by partial name match.

**Params:**
- `query` (str, optional): substring matched against opportunity name
- `limit` (int, default 20, capped at 50)

**Example prompts:**
- "Search CRM for opportunities mentioning 'banking', top 10."
- "List my 20 most recent opportunities."

**Returns:** array of objects with the CRM_FIELDS above.

---

## `crm_list_stale_opportunities`

**Purpose:** opportunities that have no scheduled next activity. Use
to find leads going cold.

**Params:**
- `limit` (int, default 20, capped at 50)

**Example prompt:**
- "Show me the 15 stalest opportunities I own."

**Returns:** same shape as search. Sorted by Odoo's default ordering.

---

## `crm_list_stages`

**Purpose:** get the stage catalog. You need the `id` from here for
`crm_update_stage`.

**Params:**
- `limit` (int, default 50, capped at 100)

**Example prompt:**
- "What CRM stages exist?"

**Returns:** rows of `{id, name, sequence, ...}`.

---

## `crm_create_lead`

**Purpose:** create a new lead.

**Params:**
- `name` (str, required) — the opportunity title
- `contact_name` (str, optional)
- `email` (str, optional)
- `phone` (str, optional)
- `description` (str, optional)

**Example prompt:**
- "Create a CRM lead: name 'Acme POC', contact 'Jane Doe',
  email '<jane@acme.com>', phone '+1 248 555 0100', description
  'Inbound via partner channel — 200 endpoint pilot.'"

**Returns:** `{id, name, ...}` of the new lead.

**Audit:** writes
`actor=you, action=create, model=crm.lead, record_id=<new_id>`
with the **field names** you set (not values).

---

## `crm_add_note`

**Purpose:** post a chatter (internal) note on an existing lead.

**Params:**
- `lead_id` (int, required)
- `note` (str, required) — plain text, supports basic Odoo chatter
  markup

**Example prompts:**
- "Add note to lead 142: 'Demo confirmed Tuesday 10am with VP Eng.'"
- "Append to lead 142: 'Customer asked about SOC2 timeline.'"

**Returns:** `{lead_id, message_id, ...}`.

**Audit:** `action=message_post, payload={body_length: <n>}`.

---

## `crm_update_stage`

**Purpose:** move a lead to a different stage.

**Params:**
- `lead_id` (int, required)
- `stage_id` (int, required) — get this from `crm_list_stages`

**Example prompt:**
- "Move lead 142 to stage 'Proposal'." *(Claude resolves the stage
  name to its id via `crm_list_stages` first.)*

**Returns:** updated lead summary.

**Audit:** `action=write.stage, payload={stage_id: <n>}`.

---

## Patterns that work well

### Daily morning sweep
> "List my 10 stalest opportunities, then for each one summarize the
> last chatter activity."

Claude calls `crm_list_stale_opportunities` then reads each lead's
chatter (CRM module on Odoo side). Result: a tight cold-list report.

### Pipeline triage with stage moves
> "Show me opportunities in stage 'Qualifying' over 30 days old."
> *(then)* "Move IDs 142, 158, 163 to stage 'Stalled'."

Two-prompt flow. First call: search + filter. Second call:
batch stage updates (Claude loops `crm_update_stage`).

### Lead intake from email/chat
> "Create a CRM lead from this email: <paste email>".

Claude extracts name/contact/email/phone and calls
`crm_create_lead`. Always confirm the parsed values before sending.

---

## Constraints

- All write tools require the actor to have edit rights on
  `crm.lead`. If you can't update a stage in the Odoo UI, the tool
  will return 403.
- `crm_create_lead` always creates as type `lead`. Promotion to
  opportunity happens via Odoo's standard stage flow.
- Search is substring on `name` only. Use Odoo's UI for advanced
  filtering (custom domains, tag-based, etc.).
- All free-text fields are truncated by Odoo at the model field
  length. The MCP layer does not truncate further.

---

## Errors you might see

| Error | Meaning | Fix |
| --- | --- | --- |
| `HTTP 403` | Record-rule denies your user | Confirm permissions in Odoo |
| `HTTP 400 invalid stage_id` | Stage doesn't exist or isn't on the lead's team | Call `crm_list_stages` first |
| `HTTP 400 Missing signature` | Server-side, not your fault | Ping platform team |
| Tool returns `[]` | No matching records — or record-rules filter them out | Verify the same query in Odoo UI |
