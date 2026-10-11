"""Event builders for the Order service (the PRODUCER of order.placed).

The consumer-driven contract test checks that what we build here satisfies what the
Inventory service says it needs (services/inventory-service/contracts).
"""
import json


def build_order_placed(order: dict) -> dict:
    return {
        "orderId": order["id"],
        "customerId": order["customer_id"],
        "items": json.loads(order["items"]),
        "amount": order["amount"],
        "currency": order["currency"],
        "paymentToken": order["payment_token"],  # tokenised reference from the PSP, never a card number
    }


def build_order_outcome(order: dict, reason: str | None = None) -> dict:
    return {"orderId": order["id"], "customerId": order["customer_id"], "status": order["status"], "reason": reason}
