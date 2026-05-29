# Expense Tools — Giggso Odoo MCP

Expense create / list / submit tools, backed by Odoo's `hr_expense` module.

## Tools

### `expense_list`
List expense lines (`hr.expense`).
- `employee_id` (int, optional)
- `state` (str, optional) — `draft`, `reported`, `approved`, `done`, `refused`
- `limit` (int, default 30, max 75)

Returns: `id, name, employee_id, product_id, total_amount, currency_id, date, state, sheet_id, payment_mode, reference`.

### `expense_create`
Create a new expense line.
- `name` (str, required) — description
- `total_amount` (float, required)
- `product_id` (int, optional) — expense product (e.g. "Travel")
- `employee_id` (int, optional) — defaults to caller's employee
- `date` (str, ISO, optional)
- `reference` (str, optional) — bill or receipt reference

Returns: `{id, message}`.

### `expense_list_sheets`
List expense sheets (reports / batches).
- `employee_id` (int, optional)
- `state` (str, optional) — `draft`, `submit`, `approve`, `post`, `done`, `cancel`
- `limit` (int, default 30, max 75)

Returns: `id, name, employee_id, state, total_amount, currency_id, expense_line_ids, accounting_date`.

### `expense_submit_sheet`
Submit an expense sheet for approval (`draft` → `submit`).
- `sheet_id` (int, required)

Returns: `{id, state, message}`.

## Example prompts (Claude)
- "Create an expense for $42 lunch on 2026-05-28."
- "List my draft expenses."
- "Submit expense sheet 87 for approval."
- "Show all expenses pending approval for employee 23."

## Notes
- `expense_create` does NOT create a sheet — it creates a line. Lines are batched into sheets in Odoo. The user (or your workflow) must group them into a sheet before submission.
- Caller must be linked to an `hr.employee` (via the employee's "Related User" field) for the default employee_id to resolve.
- Default currency is the company's. Pass `total_amount` in that currency.
