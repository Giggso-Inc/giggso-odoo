from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppServices
from .common import authenticated_login


def register_sale_tools(mcp: FastMCP, services: AppServices) -> None:
    @mcp.tool()
    def sale_list_orders(
        state: str = "",
        partner_id: int | None = None,
        query: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List sale orders / quotations visible to the authenticated user."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="sale",
            action="list_orders",
            params={
                "state": state,
                "partner_id": partner_id,
                "query": query,
                "limit": min(limit, 75),
            },
        )
        return list(result)

    @mcp.tool()
    def sale_get_order(order_id: int) -> dict[str, Any]:
        """Return a sale order header with all of its order lines."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="sale",
            action="get_order",
            params={"order_id": order_id},
        )
        return dict(result)

    @mcp.tool()
    def sale_create_quotation(
        partner_id: int,
        order_lines: list[dict[str, Any]] | None = None,
        validity_date: str = "",
        client_order_ref: str = "",
    ) -> dict[str, Any]:
        """Create a draft quotation for a partner (optional inline order lines)."""
        actor_email = authenticated_login()
        # Build the values dict from supplied fields
        values: dict[str, Any] = {"partner_id": partner_id}
        if validity_date:
            values["validity_date"] = validity_date
        if client_order_ref:
            values["client_order_ref"] = client_order_ref
        if order_lines:
            values["order_line"] = list(order_lines)
        result = services.call_odoo(
            actor_email=actor_email,
            module="sale",
            action="create_quotation",
            params={"values": values},
        )
        services.audit.write(
            actor=actor_email, action="create", model="sale.order",
            record_id=int(dict(result)["id"]), payload={"partner_id": partner_id, "line_count": len(order_lines or [])},
        )
        return dict(result)

    @mcp.tool()
    def sale_confirm_order(order_id: int) -> dict[str, Any]:
        """Confirm a quotation, turning it into a sale order."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email,
            module="sale",
            action="confirm_order",
            params={"order_id": order_id},
        )
        services.audit.write(
            actor=actor_email, action="action_confirm", model="sale.order",
            record_id=order_id, payload={"event": "confirm"},
        )
        return dict(result)

    @mcp.tool()
    def sale_add_order_line(
        order_id: int,
        product_id: int,
        product_uom_qty: float,
        price_unit: float | None = None,
        name: str = "",
    ) -> dict[str, Any]:
        """Add a line to an existing draft / sent sale order."""
        actor_email = authenticated_login()
        # Build the line values dict from supplied fields
        values: dict[str, Any] = {
            "product_id": product_id,
            "product_uom_qty": product_uom_qty,
        }
        if price_unit is not None:
            values["price_unit"] = price_unit
        if name:
            values["name"] = name
        result = services.call_odoo(
            actor_email=actor_email,
            module="sale",
            action="add_order_line",
            params={"order_id": order_id, "values": values},
        )
        services.audit.write(
            actor=actor_email, action="create", model="sale.order.line",
            record_id=int(dict(result)["id"]), payload={"order_id": order_id, "product_id": product_id},
        )
        return dict(result)

    @mcp.tool()
    def sale_list_products(
        query: str = "",
        product_type: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Search the product catalogue by name or type (service/consu/storable)."""
        actor_email = authenticated_login()
        result = services.call_odoo(
            actor_email=actor_email, module="sale", action="list_products",
            params={"query": query, "product_type": product_type, "limit": min(limit, 50)},
        )
        return list(result)
