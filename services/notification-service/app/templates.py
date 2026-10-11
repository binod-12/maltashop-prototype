TEMPLATES = {
    "order.placed": lambda p: f"We received your order {p['orderId']}. We will confirm it shortly.",
    "order.confirmed": lambda p: f"Good news - order {p['orderId']} is confirmed and paid.",
    "order.cancelled": lambda p: f"Sorry - order {p['orderId']} was cancelled ({p.get('reason') or 'unknown reason'}).",
}
