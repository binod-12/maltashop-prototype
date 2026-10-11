export const TEMPLATES = {
  'order.placed': (p) => `We received your order ${p.orderId}. We will confirm it shortly.`,
  'order.confirmed': (p) => `Good news - order ${p.orderId} is confirmed and paid.`,
  'order.cancelled': (p) => `Sorry - order ${p.orderId} was cancelled (${p.reason || 'unknown reason'}).`,
};
