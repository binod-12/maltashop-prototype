import http from 'node:http';
import { readFileSync } from 'node:fs';
import { openDb, markProcessed, tx } from './common/db.js';
import { connect, publish, subscribe, isConnected } from './common/mq.js';
import { validate } from './common/contract.js';
import { info, warn } from './common/log.js';
import { reserve, release } from './stock.js';

const PORT = Number(process.env.PORT || 3002);
const DB_PATH = process.env.DB_PATH || './data/inventory.db';
const contract = JSON.parse(readFileSync(new URL('../contracts/order-placed.consumer.json', import.meta.url)));

const db = openDb(
  DB_PATH,
  `CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, qty INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS reservations (
     order_id TEXT NOT NULL, sku TEXT NOT NULL, qty INTEGER NOT NULL, status TEXT NOT NULL
   );`
);
// seed demo stock once
for (const [sku, qty] of [['LAPTOP-15', 20], ['PHONE-X', 50], ['KETTLE-1', 100], ['LAMP-OAK', 2]]) {
  db.prepare('INSERT OR IGNORE INTO stock (sku, qty) VALUES (?, ?)').run(sku, qty);
}

// ---- minimal HTTP: health + a read-only stock view (handy for screenshots) ----
http
  .createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    if (req.url === '/health') return res.end(JSON.stringify({ status: 'ok' }));
    if (req.url === '/ready') {
      res.statusCode = isConnected() ? 200 : 503;
      return res.end(JSON.stringify({ status: isConnected() ? 'ready' : 'broker-unavailable' }));
    }
    if (req.url === '/stock') return res.end(JSON.stringify(db.prepare('SELECT * FROM stock').all()));
    if (req.url === '/reservations') return res.end(JSON.stringify(db.prepare('SELECT * FROM reservations').all()));
    res.statusCode = 404;
    res.end('{}');
  })
  .listen(PORT, () => info('service.started', `inventory-service listening on ${PORT}`));

async function main() {
  await connect();

  // Saga step 1: reserve stock when an order is placed.
  await subscribe('inventory-service.order-placed', ['order.placed'], async (payload, meta) => {
    const { correlationId } = meta;
    info('event.received', 'received order.placed', correlationId, { orderId: payload.orderId });

    const problems = validate(contract, payload);
    if (problems.length) throw new Error(`contract violation: ${problems.join('; ')}`); // -> DLQ

    const outcome = tx(db, () => {
      if (!markProcessed(db, meta.messageId, 'inventory.reserve')) return null; // redelivery
      return reserve(db, payload.orderId, payload.items);
    });
    if (outcome === null) return info('event.duplicate', 'duplicate order.placed ignored (idempotent consumer)', correlationId);

    if (outcome.ok) {
      info('inventory.reserved', `stock reserved for order ${payload.orderId}`, correlationId);
      await publish('inventory.reserved', {
        orderId: payload.orderId, amount: payload.amount, paymentToken: payload.paymentToken,
      }, correlationId);
    } else {
      warn('inventory.failed', outcome.reason, correlationId, { orderId: payload.orderId });
      await publish('inventory.failed', { orderId: payload.orderId, reason: outcome.reason }, correlationId);
    }
  });

  // Saga compensation: payment failed -> give the stock back.
  await subscribe('inventory-service.payment-failed', ['payment.failed'], async (payload, meta) => {
    const { correlationId } = meta;
    info('event.received', 'received payment.failed', correlationId, { orderId: payload.orderId });
    const released = tx(db, () => {
      if (!markProcessed(db, meta.messageId, 'inventory.release')) return null;
      return release(db, payload.orderId);
    });
    if (released === null) return info('event.duplicate', 'duplicate payment.failed ignored', correlationId);
    info('inventory.released', `compensation: released ${released} reservation line(s) for order ${payload.orderId}`, correlationId);
    await publish('inventory.released', { orderId: payload.orderId }, correlationId);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
