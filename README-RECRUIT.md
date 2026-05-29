# Recruiting Tools — Giggso Odoo MCP

Recruitment tools backed by Odoo's `hr_recruitment` module. All tools require an authenticated MCP bearer token; calls are executed as the Odoo user whose login matches the token's `client_id`.

## Tools

### `recruit_list_jobs`
List job postings.
- `query` (str, optional) — ilike filter on job title
- `limit` (int, default 20, max 50)

Returns: `id, name, department_id, user_id, state, no_of_recruitment, no_of_hired_employee`.

### `recruit_list_applicants`
List applicants.
- `job_id` (int, optional) — restrict to one job
- `query` (str, optional) — ilike filter on partner_name
- `limit` (int, default 30, max 75)

Returns: `id, name, partner_name, email_from, partner_phone, job_id, stage_id, user_id, kanban_state, create_date, date_closed, active`.

### `recruit_list_applicant_stages`
List recruitment kanban stages.
- `limit` (int, default 50, max 100)

Returns: `id, name, sequence, fold, hired_stage`.

### `recruit_create_applicant`
Create an applicant tied to a job.
- `partner_name` (str, required) — also used as the applicant name
- `job_id` (int, required)
- `email` (str, optional) — stored as `email_from`
- `phone` (str, optional) — stored as `partner_phone`
- `description` (str, optional)

Returns: `{id, message}`.

### `recruit_move_applicant_stage`
Move an applicant to another kanban stage.
- `applicant_id` (int, required)
- `stage_id` (int, required)

Returns: `{id, message}`.

### `recruit_add_applicant_note`
Add an internal chatter note to an applicant.
- `applicant_id` (int, required)
- `note` (str, required) — HTML allowed

Returns: `{id, message}`.

## Example prompts (Claude)
- "List all open job postings."
- "Who applied to job 12 in the last week?"
- "Add applicant John Doe to job 12 with email john@x.com."
- "Move applicant 47 to the 'Phone Screen' stage."
- "Add a note 'Strong portfolio' to applicant 47."

## Odoo permissions
Caller must have at least Recruiter access on `hr.recruitment`. Without it, write tools will return an Odoo `AccessError`.
