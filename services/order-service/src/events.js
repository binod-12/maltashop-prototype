// Event builders for the Order service (the PRODUCER of order.placed).
// The consumer-driven contract test checks that what we build here satisfies what
// the Inventory service says it needs (services/inventory-service/contracts).
export function buildOrderPlaced(order) {
  return {
    orderId: order.id,
    customerId: order.customer_id,
    items: JSON.parse(order.items),
    amount: order.amount,
    currency: order.currency,
    paymentToken: order.payment_token, // tokenised reference from the PSP, never a card number
  };
}

export function buildOrderOutcome(order, reason = null) {
  return { orderId: order.id, customerId: order.customer_id, status: order.status, reason };
}
