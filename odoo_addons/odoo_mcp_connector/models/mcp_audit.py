from odoo import fields, models


class OdooMcpAudit(models.Model):
    _name = "odoo.mcp.audit"
    _description = "Odoo MCP Audit Event"
    _order = "create_date desc"

    actor_email = fields.Char(required=True, index=True)
    action = fields.Char(required=True, index=True)
    module = fields.Char(required=True, index=True)
    model_name = fields.Char(index=True)
    record_id = fields.Integer()
    success = fields.Boolean(default=True, index=True)
    detail = fields.Text()
