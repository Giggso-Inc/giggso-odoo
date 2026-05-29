# Timesheet Tools — Giggso Odoo MCP

Time-entry tools backed by Odoo's `hr_timesheet` module. Underlying model is `account.analytic.line` filtered to entries with a `project_id`.

## Tools

### `timesheet_list`
List timesheet entries.
- `employee_id` (int, optional)
- `project_id` (int, optional)
- `date_from` (str, ISO date, optional)
- `date_to` (str, ISO date, optional)
- `limit` (int, default 30, max 75)

Returns: `id, name, date, unit_amount, project_id, task_id, employee_id, user_id`.

### `timesheet_create_entry`
Log work hours on a project (and optionally a task).
- `project_id` (int, required)
- `unit_amount` (float, required) — hours
- `name` (str, optional) — description; default `/`
- `task_id` (int, optional)
- `date` (str, ISO date, optional) — defaults to today
- `employee_id` (int, optional) — defaults to caller's employee

Returns: `{id, message}`.

### `timesheet_weekly_summary`
This-week totals for the caller's employee (Monday–Sunday, server timezone).
- (no params)

Returns: `{employee_id, week_start, week_end, entries, total_hours}`.

## Example prompts (Claude)
- "Log 4 hours to project 5 task 132 with the note 'Red-team plan review'."
- "How many hours did I log this week?"
- "Show all entries for project 5 from last Monday to today."
- "Did employee 23 timesheet anything this week?"

## Notes
- Caller must be linked to an `hr.employee` via the employee's "Related User" field.
- Use `name = "/"` (Odoo's standard placeholder) when no description is provided — already handled by the default.
- Editing or deleting existing timesheet entries is intentionally not exposed via MCP to keep audit trails intact.
