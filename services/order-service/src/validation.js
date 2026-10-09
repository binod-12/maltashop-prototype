// Request validation for POST /orders. Pure function so it can be unit tested without a server.
export function validateOrderRequest(body) {
  const errors = [];
  if (!body || typeof body !== 'object') return ['body must be a JSON object'];
  if (typeof body.customerId !== 'string' || body.customerId.length === 0) errors.push('customerId is required');
  if (!Array.isArray(body.items) || body.items.length === 0) {
    errors.push('items must be a non-empty array');
  } else {
    body.items.forEach((it, i) => {
      if (typeof it.sku !== 'string' || !it.sku) errors.push(`items[${i}].sku is required`);
      if (!Number.isInteger(it.qty) || it.qty < 1) errors.push(`items[${i}].qty must be a positive integer`);
    });
  }
  if (typeof body.amount !== 'number' || !(body.amount > 0)) errors.push('amount must be a positive number');
  if (typeof body.paymentToken !== 'string' || !body.paymentToken) errors.push('paymentToken is required');
  return errors;
}
