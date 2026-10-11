import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { chargeWithProvider } from './provider.js';
import { openDb, markProcessed, tx } from './common/db.js';
import { connect, publish, subscribe, isConnected } from './common/mq.js';
import { info, warn } from './common/log.js';

const PORT = Number(process.env.PORT || 3003);
const DB_PATH = process.env.DB_PATH || './data/payments.db';

const db = openDb(
  DB_PATH,
  `CREATE TABLE IF NOT EXISTS payments (
     id TEXT PRIMARY KEY,
     order_id TEXT NOT NULL UNIQUE,      -- one payment per order = natural idempotency key
     amount REAL NOT NULL,
     status TEXT NOT NULL,               -- COMPLETED | FAILED
     provider_ref TEXT,
     created_at TEXT NOT NULL
   );`
);

http
  .createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    if (req.url === '/health') return res.end(JSON.stringify({ status: 'ok' }));
    if (req.url === '/ready') {
      res.statusCode = isConnected() ? 200 : 503;
      return res.end(JSON.stringify({ status: isConnected() ? 'ready' : 'broker-unavailable' }));
    }
    if (req.url === '/payments') return res.end(JSON.stringify(db.prepare('SELECT * FROM payments').all()));
    res.statusCode = 404;
    res.end('{}');
  })
  .listen(PORT, () => info('service.started', `payment-service listening on ${PORT}`));

async function main() {
  await connect();

  // Saga step 2: stock is reserved -> take payment.
  await subscribe('payment-service.inventory-reserved', ['inventory.reserved'], async (payload, meta) => {
    const { correlationId } = meta;
    info('event.received', 'received inventory.reserved', correlationId, { orderId: payload.orderId });

    // Idempotency: if we already handled this order, re-publish nothing and do not charge twice.
    const seen = tx(db, () => !markProcessed(db, meta.messageId, 'payment.charge'));
    if (seen) return info('event.duplicate', 'duplicate inventory.reserved ignored - no double charge', correlationId);

    const result = await chargeWithProvider(payload.paymentToken, payload.amount);
    const id = randomUUID();
    db.prepare('INSERT OR IGNORE INTO payments (id, order_id, amount, status, provider_ref, created_at) VALUES (?, ?, ?, ?, ?, ?)')
      .run(id, payload.orderId, payload.amount, result.ok ? 'COMPLETED' : 'FAILED', result.providerRef || null, new Date().toISOString());

    if (result.ok) {
      info('payment.completed', `payment ${id} completed for order ${payload.orderId}`, correlationId);
      await publish('payment.completed', { orderId: payload.orderId, paymentId: id, amount: payload.amount }, correlationId);
    } else {
      warn('payment.failed', result.reason, correlationId, { orderId: payload.orderId });
      await publish('payment.failed', { orderId: payload.orderId, reason: result.reason }, correlationId);
    }
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
