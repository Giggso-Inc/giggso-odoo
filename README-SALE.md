# Sales Tools — Giggso Odoo MCP

Sale order tools backed by Odoo's `sale_management` module.

## Tools

### `sale_list_orders`
List sale orders / quotations.
- `state` (str, optional) — `draft`, `sent`, `sale`, `done`, `cancel`
- `partner_id` (int, optional)
- `query` (str, optional) — ilike on order name (e.g. "SO00012")
- `limit` (int, default 30, max 75)

Returns: `id, name, partner_id, user_id, team_id, state, date_order, amount_total, currency_id, invoice_status, validity_date`.

### `sale_get_order`
Return one sale order header plus all its order lines.
- `order_id` (int, required)

Returns the header fields plus `order_line: [{id, order_id, product_id, name, product_uom_qty, price_unit, price_subtotal, tax_id}, ...]`.

### `sale_create_quotation`
Create a draft quotation for a partner. Optionally supply order lines inline.
- `partner_id` (int, required)
- `order_lines` (list of dicts, optional) — each line: `{product_id, product_uom_qty, [price_unit], [name]}`
- `validity_date` (str, ISO date, optional)
- `client_order_ref` (str, optional) — customer PO reference

Returns: `{id, name, message}`.

### `sale_confirm_order`
Confirm a quotation (state `draft` / `sent` → `sale`).
- `order_id` (int, required)

Returns: `{id, state, message}`.

### `sale_add_order_line`
Append a line to an existing draft / sent order.
- `order_id` (int, required)
- `product_id` (int, required)
- `product_uom_qty` (float, required)
- `price_unit` (float, optional) — falls back to product list price
- `name` (str, optional) — falls back to product display name

Returns: `{id, order_id, message}`.

## Example prompts (Claude)
- "Create a quotation for partner 8421 with 5 units of product 137."
- "Show me all draft quotations."
- "Add 3 of product 142 to order 9043."
- "Confirm quotation 9043 and tell me the new state."
- "What's the total amount on order 9043?"

## Notes
- Quotations created via `sale_create_quotation` are draft. Pricing and taxes are filled in by Odoo from the product and partner pricelist.
- `sale_add_order_line` refuses to add lines on confirmed orders (`state` ∉ {`draft`, `sent`}) — by design; modify via the Odoo UI for confirmed orders.
- The caller must have access to the relevant sales team. Without it, `list_orders` returns an empty list and `create_quotation` raises an `AccessError`.
