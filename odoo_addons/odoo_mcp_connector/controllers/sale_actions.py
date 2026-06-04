# ============================================================
# File: sale_actions.py
# Summary: Odoo controller actions for sale.order + sale.order.line.
#          Create / list / confirm / add-line helpers callable via
#          the signed MCP connector.
# Version: 19.0.1.0.0
# ============================================================

from __future__ import annotations

from typing import Any

from odoo.http import request

from .utils import compact_records


# Fields surfaced for sale orders.
ORDER_FIELDS = [
    "id",
    "name",
    "partner_id",
    "user_id",
    "team_id",
    "state",
    "date_order",
    "amount_total",
    "currency_id",
    "invoice_status",
    "validity_date",
]

# Fields surfaced for sale order lines.
ORDER_LINE_FIELDS = [
    "id",
    "order_id",
    "product_id",
    "name",
    "product_uom_qty",
    "price_unit",
    "price_subtotal",
    "tax_id",
]


def list_orders(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List sale orders / quotations visible to the mapped user."""
    domain: list[Any] = []
    if params.get("state"):
        domain.append(("state", "=", params["state"]))
    if params.get("partner_id"):
        domain.append(("partner_id", "=", int(params["partner_id"])))
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))
    records = request.env["sale.order"].with_user(user).search_read(
        domain,
        ORDER_FIELDS,
        limit=int(params.get("limit", 30)),
        order="date_order desc",
    )
    return compact_records(records)


def get_order(user, params: dict[str, Any]) -> dict[str, Any]:
    """Return a single sale order with its lines."""
    order = (
        request.env["sale.order"]
        .with_user(user)
        .browse(int(params["order_id"]))
        .exists()
    )
    if not order:
        raise ValueError("Sale order not found or not visible")
    head = compact_records(order.read(ORDER_FIELDS))[0]
    lines = compact_records(order.order_line.read(ORDER_LINE_FIELDS))
    head["order_line"] = lines
    return head


def create_quotation(user, params: dict[str, Any]) -> dict[str, Any]:
    """Create a draft sale order (quotation)."""
    values = dict(params["values"])
    # Optionally inline order lines under "order_line"
    if "order_line" in values and isinstance(values["order_line"], list):
        # Convert each plain dict to (0, 0, vals) one2many command tuple
        values["order_line"] = [(0, 0, dict(line)) for line in values["order_line"]]
    order = request.env["sale.order"].with_user(user).create(values)
    return {"id": order.id, "name": order.name, "message": "Quotation created"}


def confirm_order(user, params: dict[str, Any]) -> dict[str, Any]:
    """Confirm a quotation (draft -> sale order via action_confirm)."""
    order = (
        request.env["sale.order"]
        .with_user(user)
        .browse(int(params["order_id"]))
        .exists()
    )
    if not order:
        raise ValueError("Sale order not found or not visible")
    order.action_confirm()
    return {"id": order.id, "state": order.state, "message": "Order confirmed"}


def list_products(user, params: dict[str, Any]) -> list[dict[str, Any]]:
    """List sellable products visible to the mapped user."""
    domain: list[Any] = [("sale_ok", "=", True), ("active", "=", True)]
    if params.get("query"):
        domain.append(("name", "ilike", params["query"]))
    if params.get("product_type"):
        domain.append(("type", "=", params["product_type"]))
    records = request.env["product.template"].with_user(user).search_read(
        domain,
        ["id", "name", "list_price", "type", "categ_id", "uom_id"],
        limit=int(params.get("limit", 30)),
        order="name asc",
    )
    from .utils import compact_records
    return compact_records(records)


def add_order_line(user, params: dict[str, Any]) -> dict[str, Any]:
    """Append a sale.order.line to an existing draft/sent order."""
    order = (
        request.env["sale.order"]
        .with_user(user)
        .browse(int(params["order_id"]))
        .exists()
    )
    if not order:
        raise ValueError("Sale order not found or not visible")
    if order.state not in ("draft", "sent"):
        raise ValueError("Can only add lines to draft or sent orders")
    values = dict(params["values"])
    values["order_id"] = order.id
    line = request.env["sale.order.line"].with_user(user).create(values)
    return {"id": line.id, "order_id": order.id, "message": "Order line added"}
def delete_order_line(user, params: dict[str, Any]) -> dict[str, Any]:
    """Delete a line from draft/sent order. Recalculates order totals."""
    order = request.env["sale.order"].with_user(user).browse(int(params["order_id"])).exists()
    if not order:
        raise ValueError("Sale order not found or not visible")
    if order.state not in ("draft", "sent"):
        raise ValueError("Can only delete lines from draft or sent orders")
    line = order.order_line.filtered(lambda l: l.id == int(params["line_id"]))
    if not line:
        raise ValueError("Order line not found in this order")
    line_id = line.id
    line.unlink()
    return {"order_id": order.id, "line_id": line_id, "message": "Order line deleted"}
