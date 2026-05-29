{
    "name": "Odoo MCP Connector",
    "version": "19.0.2.0.0",
    "summary": "Secure MCP connector for CRM, Project, Recruiting, HR, Attendance, Expense, Timesheet, and Sales",
    "author": "Giggso",
    "website": "https://giggso.com",
    "category": "Productivity",
    "license": "LGPL-3",
    # Hard depends are modules we know exist in the target DB.
    # hr_attendance / hr_recruitment / hr_expense / hr_timesheet / sale_management
    # are listed here because the connector exposes tools for them. If any are
    # missing, the addon install will fail loudly instead of silently breaking
    # individual tools at runtime.
    "depends": [
        "base",
        "mail",
        "crm",
        "project",
        "hr",
        "hr_recruitment",
        "hr_attendance",
        "hr_expense",
        "hr_timesheet",
        "sale_management",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": True,
}
