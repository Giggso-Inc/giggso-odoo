# Gap Analysis — Project Task Filtering
**Date:** 2026-07-29  
**Author:** Raven review  
**Scope:** `project_list_tasks` MCP tool — inability to filter by stage/state, creation date, or assignee  
**Status:** No code changed — analysis only

---

## Problem Statement

The MCP tool `project_list_tasks` cannot answer any of these real queries:

| User intent | What they ask | What fails |
|---|---|---|
| "Show me tasks In Progress" | filter by Kanban stage | no stage param |
| "What was created today?" | filter by create date | no date param, field not returned |
| "What's assigned to Alice?" | filter by assignee email | no assignee param |

All three fail silently — the tool returns unfiltered results rather than erroring.

---

## Architecture: Two-Layer Stack

Every filter must be wired at **both** layers or it is a dead end:

```
Claude → MCP Tool (projects.py)         ← Layer 1: accepts params, builds connector call
            ↓
         Odoo Addon (project_actions.py) ← Layer 2: builds ORM domain, runs search_read
```

---

## Gap 1 — `project_list_tasks` MCP tool: no filter parameters

**File:** `odoo_mcp_server/src/odoo_mcp/tools/projects.py:47-61`

```python
def project_list_tasks(
    project_id: int | None = None,
    query: str = "",           # ← name search only
    limit: int = 30,
) -> list[dict[str, Any]]:
```

**Missing parameters:**

| Parameter | Type | Maps to |
|---|---|---|
| `stage_id` | `int \| None` | Kanban column filter |
| `stage_name` | `str` | Kanban column by name (friendlier) |
| `assignee_email` | `str` | Filter by assigned user |
| `created_after` | `str` | ISO date — "from today", "this week" |
| `created_before` | `str` | ISO date upper bound |
| `state` | `str` | Personal task state (`in_progress`, `done`, `cancelled`, etc.) |

**Impact:** Even if Layer 2 supports these filters, they can never be invoked because the MCP tool never passes them down.

---

## Gap 2 — `list_tasks` Odoo handler: domain builder ignores filter params

**File:** `odoo_addons/odoo_mcp_connector/controllers/project_actions.py:45-58`

```python
def list_tasks(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    domain: list[Any] = []
    if params.get("project_id"):
        domain.append(("project_id", "=", int(params["project_id"])))
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))
    # ← nothing else. stage, assignee, date, state are silently ignored
    records = request.env["project.task"].with_user(user).search_read(
        domain, TASK_FIELDS, ...
    )
```

**Missing domain clauses:**

| Param | ORM domain clause | Notes |
|---|---|---|
| `stage_id` | `("stage_id", "=", stage_id)` | Direct ID match |
| `stage_name` | `("stage_id.name", "ilike", stage_name)` | Name match — resolves id internally |
| `assignee_email` | `("user_ids.email", "=", email)` or `("user_ids.login", "=", email)` | Many2many traversal |
| `created_after` | `("create_date", ">=", date_str)` | ISO 8601 string |
| `created_before` | `("create_date", "<=", date_str)` | ISO 8601 string |
| `state` | `("state", "=", state_value)` | Odoo 17+ personal state enum |

**Impact:** Params sent from Layer 1 arrive but are silently dropped.

---

## Gap 3 — `TASK_FIELDS` missing `create_date`

**File:** `odoo_addons/odoo_mcp_connector/controllers/project_actions.py:19-30`

```python
TASK_FIELDS = [
    "id", "name", "project_id", "stage_id", "user_ids",
    "partner_id", "date_deadline", "priority", "state", "activity_state",
    # ← "create_date" is absent
]
```

**Impact:** Even if a caller receives a task list, they cannot determine when each task was created. "Tasks created today" cannot be answered server-side (missing filter) OR client-side (missing field).

Note: `TASK_DETAIL_FIELDS` (used by `get_task`) does include `create_date` — the gap is only in the list endpoint.

---

## Gap 4 — `project_list_tasks` passes only three params to connector

**File:** `odoo_mcp_server/src/odoo_mcp/tools/projects.py:55-59`

```python
result = services.call_odoo(
    actor_email=actor_email,
    module="project",
    action="list_tasks",
    params={"project_id": project_id, "query": query, "limit": min(limit, 75)},
    # ← any future filter param added to the tool signature must be
    #   explicitly added here too, or it never reaches the addon
)
```

This is a wiring gap: even after fixing Layer 1 and Layer 2, a developer must remember to pass new params in this dict. It is easy to miss.

---

## Gap 5 — No `stage_name` lookup utility in the addon

When a user says "show me tasks In Progress", they mean a stage by name, not by ID. Resolving a stage name to a `stage_id` for a given project requires a `project.task.type` lookup. That lookup does not exist in any shared utility — each caller would have to repeat it.

**Relevant existing code:** `list_task_stages` can return the stages, but the consumer (Claude or a script) must do a two-call dance:
1. `project_list_task_stages(project_id=X)` → get stage id for "In Progress"
2. `project_list_tasks(project_id=X, stage_id=<id>)` → get tasks

This is functional but poor UX. A `stage_name` param that resolves internally would avoid the round-trip.

---

## Gap Summary Table

| Gap | Layer | File | Severity |
|---|---|---|---|
| No `stage_id` / `stage_name` filter param | MCP Tool | `tools/projects.py` | High |
| No `assignee_email` filter param | MCP Tool | `tools/projects.py` | High |
| No `created_after` / `created_before` filter param | MCP Tool | `tools/projects.py` | High |
| No `state` filter param | MCP Tool | `tools/projects.py` | Medium |
| Domain builder ignores all filter params | Odoo Addon | `project_actions.py` | High |
| `create_date` absent from `TASK_FIELDS` | Odoo Addon | `project_actions.py` | Medium |
| New params not wired into `call_odoo` params dict | MCP Tool | `tools/projects.py` | High |
| No `stage_name → stage_id` resolver utility | Odoo Addon | `project_actions.py` | Low |

---

## Fix Plan

### Phase 1 — Odoo Addon (Layer 2)

**File:** `odoo_addons/odoo_mcp_connector/controllers/project_actions.py`

**Step 1.1 — Add `create_date` to `TASK_FIELDS`**

```python
TASK_FIELDS = [
    "id", "name", "project_id", "stage_id", "user_ids",
    "partner_id", "date_deadline", "priority", "state",
    "activity_state", "create_date",           # ← add this
]
```

No behaviour change — just adds the field to list responses.

**Step 1.2 — Extend `list_tasks` domain builder**

Add four new optional params handled inside `list_tasks()`:

```python
# stage filter — by ID or by name
if params.get("stage_id"):
    domain.append(("stage_id", "=", int(params["stage_id"])))
elif params.get("stage_name"):
    domain.append(("stage_id.name", "ilike", str(params["stage_name"])))

# assignee filter — match login or email via Many2many traversal
if params.get("assignee_email"):
    email = str(params["assignee_email"]).strip()
    domain += ["|",
        ("user_ids.login", "=", email),
        ("user_ids.email", "=", email),
    ]

# creation date window
if params.get("created_after"):
    domain.append(("create_date", ">=", str(params["created_after"])))
if params.get("created_before"):
    domain.append(("create_date", "<=", str(params["created_before"])))

# personal state (Odoo 17+ enum: in_progress, changes_requested,
# approved, cancelled, done)
if params.get("state"):
    domain.append(("state", "=", str(params["state"])))
```

No handler registration changes needed — `list_tasks` is already in `HANDLERS`.

---

### Phase 2 — MCP Tool (Layer 1)

**File:** `odoo_mcp_server/src/odoo_mcp/tools/projects.py`

**Step 2.1 — Add filter params to `project_list_tasks` signature**

```python
def project_list_tasks(
    project_id: int | None = None,
    query: str = "",
    stage_id: int | None = None,
    stage_name: str = "",
    assignee_email: str = "",
    created_after: str = "",    # ISO date: "2026-07-29" or "2026-07-29T00:00:00"
    created_before: str = "",
    state: str = "",            # in_progress | changes_requested | approved |
                                 # cancelled | done
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List tasks visible to the given Odoo user.

    Filters (all optional, combinable):
    - project_id: restrict to one project
    - query: name contains (case-insensitive)
    - stage_id: exact Kanban stage ID
    - stage_name: Kanban stage name (partial match, e.g. "In Progress")
    - assignee_email: tasks assigned to this user login or email
    - created_after / created_before: ISO 8601 date strings
    - state: personal task state (in_progress, done, cancelled, …)
    """
```

**Step 2.2 — Wire all params into `call_odoo` params dict**

```python
result = services.call_odoo(
    actor_email=actor_email,
    module="project",
    action="list_tasks",
    params={
        "project_id": project_id,
        "query": query,
        "stage_id": stage_id,
        "stage_name": stage_name,
        "assignee_email": assignee_email,
        "created_after": created_after,
        "created_before": created_before,
        "state": state,
        "limit": min(limit, 75),
    },
)
```

---

### Phase 3 — Tests

**File:** `odoo_addons/odoo_mcp_connector/tests/test_project_actions.py`

Add to existing test class:

| Test | Asserts |
|---|---|
| `test_list_tasks_filter_by_stage_id` | domain contains `("stage_id", "=", 5)` |
| `test_list_tasks_filter_by_stage_name` | domain contains `("stage_id.name", "ilike", "In Progress")` |
| `test_list_tasks_filter_by_assignee_email` | domain contains `\|` + login + email clauses |
| `test_list_tasks_filter_by_created_after` | domain contains `("create_date", ">=", "2026-07-29")` |
| `test_list_tasks_filter_by_state` | domain contains `("state", "=", "in_progress")` |
| `test_list_tasks_no_filters_returns_all` | domain is empty (no unintended filters) |
| `test_task_fields_includes_create_date` | `"create_date"` in `TASK_FIELDS` constant |

---

### Phase 4 — Documentation update

**File:** `README-PROJECT.md`

Update the `project_list_tasks` tool entry to document the new filter parameters with example prompts:

- *"Show me tasks in stage 'In Progress' in project 22"*
- *"What tasks were created today?"* → pass `created_after=<today's ISO date>`
- *"Tasks assigned to alice@giggso.com"*

---

## Execution Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4
  (addon)   (tool)   (tests)   (docs)
```

Phase 1 and Phase 2 must ship together — deploying either alone leaves one layer broken.

---

## Files Touched

| File | Change |
|---|---|
| `odoo_addons/odoo_mcp_connector/controllers/project_actions.py` | Add `create_date` to `TASK_FIELDS`; extend domain builder |
| `odoo_mcp_server/src/odoo_mcp/tools/projects.py` | Add 6 filter params; wire into `call_odoo` dict |
| `odoo_addons/odoo_mcp_connector/tests/test_project_actions.py` | 7 new test cases |
| `README-PROJECT.md` | Document new params with examples |

Total estimated diff: ~60 lines added, 0 deleted.
