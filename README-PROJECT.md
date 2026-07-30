# README — Project Management Tools

Version: 1.0 · Last verified: 2026-05-29 · Surfaced through Claude.ai

Every Project tool runs under **your Odoo identity** via the MCP
connector. You only see and change what your Odoo user can. Writes
are audited.

> Connect first via **README-USER.md**.

---

## Available tools

| Tool | Reads/Writes | One-line purpose |
| --- | --- | --- |
| `project_list_projects` | read | List projects (optionally filtered by name) |
| `project_list_tasks` | read | List tasks — filter by project, stage, assignee, date, state |
| `project_list_task_stages` | read | Stage catalog (for `stage_id` refs) |
| `project_create_task` | write | Create a task under a project |
| `project_move_task_stage` | write | Move a task between Kanban stages |
| `project_add_comment` | write | Post a chatter comment on a task |

**Project fields returned:** `id, name, user_id, partner_id, company_id`.

**Task fields returned:** `id, name, project_id, stage_id, user_ids,
partner_id, date_deadline, priority, state, activity_state, create_date`.

> Note: in Odoo 17+ the legacy `kanban_state` column was removed. We
> read `state` instead — values like `01_in_progress`,
> `02_changes_requested`, `03_approved`, `04_cancelled`,
> `1_done`, `1_canceled` (depends on your stage config).

---

## `project_list_projects`

**Purpose:** discover projects you can access.

**Params:**
- `query` (str, optional) — substring match on project name
- `limit` (int, default 20, capped at 50)

**Example prompts:**
- "List all my projects."
- "Find projects with 'Trinity' in the name."

**Returns:** array of `{id, name, user_id, partner_id, company_id}`.

---

## `project_list_tasks`

**Purpose:** list tasks with server-side filtering. All params are optional and combinable.

**Params:**

| Param | Type | Description |
|---|---|---|
| `project_id` | int | Restrict to one project. Omit for all visible projects. |
| `query` | str | Task name substring (case-insensitive). |
| `stage_id` | int | Exact Kanban stage ID. Use `project_list_task_stages` to look up IDs. |
| `stage_name` | str | Kanban stage name partial match, e.g. `"In Progress"`. Used when `stage_id` is absent. |
| `assignee_email` | str | Return only tasks assigned to this user (matches Odoo login or email). |
| `created_after` | str | ISO 8601 date — tasks created on or after this date, e.g. `"2026-07-29"`. |
| `created_before` | str | ISO 8601 date — tasks created on or before this date. |
| `state` | str | Personal task state: `in_progress` · `changes_requested` · `approved` · `cancelled` · `done`. |
| `limit` | int | Default 30, capped at 75. |

**Example prompts:**
- "Show me tasks in stage 'In Progress' in project 22."
- "What tasks were created today?" → `created_after="2026-07-29"`
- "List tasks assigned to alice@giggso.com."
- "Show done tasks in project 5 assigned to bob@giggso.com."
- "Show all tasks named 'review' across my projects, limit 20."

**Returns:** array of task objects — `id, name, project_id, stage_id, user_ids,
partner_id, date_deadline, priority, state, activity_state, create_date`.

---

## `project_list_task_stages`

**Purpose:** get the Kanban stage catalog. You need an `id` from here
to move tasks.

**Params:**
- `project_id` (int, optional) — most stages are project-scoped, so
  pass the project to get its specific stage list
- `limit` (int, default 50, capped at 100)

**Example prompt:**
- "Show me the task stages for project 5."

**Example response:**
```
Ideation · In-Progress · Dev Testing · UAT Testing · Completed · Reopened
```

---

## `project_create_task`

**Purpose:** create a task.

**Params:**
- `project_id` (int, required)
- `name` (str, required)
- `description` (str, optional)
- `deadline` (str, optional) — `YYYY-MM-DD`

**Example prompts:**
- "Create a task in project 5 named 'Draft pen-test report' due
  2026-06-15."
- "In project 12, add task 'Customer kickoff prep' with description
  'Slides + demo env + handoff doc'."

**Returns:** `{id, name, project_id, ...}` of the new task.

**Audit:**
`actor=you, action=create, model=project.task, record_id=<new_id>`,
payload lists the field names you set.

---

## `project_move_task_stage`

**Purpose:** move a task to another stage.

**Params:**
- `task_id` (int, required)
- `stage_id` (int, required) — from `project_list_task_stages`

**Example prompt:**
- "Move task 88 to stage 'UAT Testing'." *(Claude resolves the stage
  name via `project_list_task_stages` first.)*

**Returns:** updated task summary.

**Audit:** `action=write.stage, payload={stage_id: <n>}`.

---

## `project_add_comment`

**Purpose:** post a chatter comment on a task.

**Params:**
- `task_id` (int, required)
- `comment` (str, required)

**Example prompts:**
- "Add comment to task 88: 'Blocked on customer VPN — waiting for
  network team.'"
- "Comment on task 88: '@platform please review the migration plan.'"

**Returns:** `{task_id, message_id, ...}`.

**Audit:** `action=message_post, payload={body_length: <n>}`.

---

## Patterns that work well

### Standup prep
> "Show me my open tasks across all projects, then group them by
> stage."

Claude calls `project_list_tasks` (no project filter, you as
assignee implicit via Odoo permissions) and renders a grouped view.

### Sprint move
> "List all 'Dev Testing' tasks in project 5, then move them to 'UAT
> Testing'."

Two-step: list, confirm, batch-move. Always confirm the id list
before approving the writes.

### Cross-project status
> "List projects, then for each, show the 3 oldest open tasks."

Claude loops: `project_list_projects` → for each id,
`project_list_tasks(project_id=…, limit=3)`.

---

## Constraints

- You can only act on tasks your Odoo user can see/edit.
- Stages are project-scoped; don't reuse a `stage_id` from one
  project on a task in another.
- `priority` and `state` reads only — there are no `set_priority`
  tools (yet); use the Odoo UI or open an issue.
- `deadline` accepts `YYYY-MM-DD`; times are stored at 00:00 in
  the project's timezone.
- All free-text fields are truncated by Odoo at the model field
  length. The MCP layer does not truncate further.

---

## Errors you might see

| Error | Meaning | Fix |
| --- | --- | --- |
| `HTTP 400` and field name in body | A field we asked for doesn't exist on this Odoo version | File an issue — TASK_FIELDS needs updating |
| `HTTP 403` | You don't have edit rights on the task | Confirm in Odoo UI |
| `HTTP 400 invalid project_id` | Project doesn't exist or you can't access | Call `project_list_projects` first |
| Tool returns `[]` | No matching tasks or rules filter them | Verify the same query in Odoo UI |
| `HTTP 400 Missing signature` | Platform issue | Ping platform team |

---

## What's not here yet

These are on the roadmap; track in `ROADMAP.md`:
- Task reassignment (`user_ids` write)
- Bulk operations (create N tasks in one call)
- Time-tracking integration (`account.analytic.line`)
- Subtask creation
- Tag / label management
