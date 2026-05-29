# HR / Employee Tools — Giggso Odoo MCP

Read-only tools for employee and department lookups, backed by Odoo's `hr` module.

## Tools

### `hr_list_employees`
List employees.
- `query` (str, optional) — ilike filter on employee name
- `department_id` (int, optional)
- `limit` (int, default 30, max 75)

Returns: `id, name, work_email, work_phone, mobile_phone, job_title, job_id, department_id, parent_id, company_id, active`.

### `hr_get_employee`
Return one employee record.
- `employee_id` (int, required)

Returns the same fields as the list call.

### `hr_list_departments`
List departments.
- `query` (str, optional)
- `limit` (int, default 30, max 75)

Returns: `id, name, complete_name, manager_id, parent_id, company_id, total_employee`.

## Example prompts (Claude)
- "Show all employees in the Engineering department."
- "Who manages employee 23?"
- "List all departments."
- "Get full record for employee 47."

## Odoo permissions
Caller must have at least `Officer / Read all` on Employees. Standard users see only their own record and direct reports unless granted broader access.

## Note
No write tools are exposed in this module. Creating employees, departments, or contracts is intentionally not surfaced via MCP because those records carry HRIS-sensitive fields (national_id, bank, salary). Add a write tool only after the data classification review.
