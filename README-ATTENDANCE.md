# Attendance Tools — Giggso Odoo MCP

Check-in / check-out and attendance lookup tools, backed by Odoo's `hr_attendance` module.

## Tools

### `attendance_check_in`
Open a new attendance for the caller (`check_in = now UTC`, `check_out = empty`).
- (no params)

Returns: `{id, message}`.

Errors:
- "Employee already has an open attendance" — caller already has an unclosed entry; call `attendance_check_out` first.
- "No employee record linked to this Odoo user" — caller's Odoo user has no `hr.employee` record.

### `attendance_check_out`
Close the caller's currently open attendance (`check_out = now UTC`).
- (no params)

Returns: `{id, message}`.

### `attendance_list`
List attendance records.
- `employee_id` (int, optional) — restrict to one employee
- `date_from` (str, ISO date, optional)
- `date_to` (str, ISO date, optional)
- `limit` (int, default 30, max 75)

Returns: `id, employee_id, check_in, check_out, worked_hours`.

### `attendance_today_summary`
Today's attendance entries + total worked hours for the caller's employee.
- (no params)

Returns: `{employee_id, entries: [...], total_worked_hours}`.

## Example prompts (Claude)
- "Check me in."
- "Check me out and show my total hours today."
- "Show my attendance for the past 7 days."
- "List attendance for employee 23 this week."

## Notes
- Times are recorded in UTC, not the user's local timezone. Convert at display time.
- `worked_hours` is auto-computed by Odoo when `check_out` is set.
- The caller's Odoo user must be linked to an `hr.employee` (set the employee's "Related User"). Check-in / out / today-summary fail without that link.
