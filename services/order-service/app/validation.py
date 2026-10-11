"""Request validation for POST /orders. Pure function so it can be unit tested without a server."""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_order_request(body) -> list[str]:
    if not isinstance(body, dict):
        return ["body must be a JSON object"]
    errors: list[str] = []
    cid = body.get("customerId")
    if not isinstance(cid, str) or not cid:
        errors.append("customerId is required")
    items = body.get("items")
    if not isinstance(items, list) or len(items) == 0:
        errors.append("items must be a non-empty array")
    else:
        for i, it in enumerate(items):
            it = it if isinstance(it, dict) else {}
            if not isinstance(it.get("sku"), str) or not it.get("sku"):
                errors.append(f"items[{i}].sku is required")
            if not _is_int(it.get("qty")) or it["qty"] < 1:
                errors.append(f"items[{i}].qty must be a positive integer")
    amount = body.get("amount")
    if not _is_number(amount) or not amount > 0:
        errors.append("amount must be a positive number")
    token = body.get("paymentToken")
    if not isinstance(token, str) or not token:
        errors.append("paymentToken is required")
    return errors
