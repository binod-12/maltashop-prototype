// Demonstrates idempotent consumers (report 6.1): re-publish an order.placed event with the SAME
// messageId, as RabbitMQ would on a redelivery after a consumer crash. Nothing should happen twice.
// Usage: node scripts/replay-duplicate.mjs <orderId> <messageId> <correlationId>
import { createRequire } from 'node:module';
const require = createRequire(new URL('../services/order-service/package.json', import.meta.url));
const amqp = require('amqplib');

const [orderId, messageId, correlationId] = process.argv.slice(2);
if (!orderId || !messageId || !correlationId) {
  console.error('usage: node scripts/replay-duplicate.mjs <orderId> <messageId> <correlationId>');
  process.exit(1);
}
const url = process.env.RABBITMQ_URL || 'amqp://maltashop:maltashop_dev@localhost:5672';
const order = await (await fetch(`${process.env.ORDER_URL || 'http://localhost:3001'}/orders/${orderId}`)).json();

const conn = await amqp.connect(url);
const ch = await conn.createConfirmChannel();
const payload = {
  orderId: order.id, customerId: order.customer_id, items: order.items,
  amount: order.amount, currency: order.currency, paymentToken: 'tok_ok',
};
ch.publish('maltashop.events', 'order.placed', Buffer.from(JSON.stringify(payload)),
  { persistent: true, messageId, correlationId, contentType: 'application/json' });
await ch.waitForConfirms();
console.log(`re-published order.placed for ${orderId} with the same messageId ${messageId}`);
await conn.close();
