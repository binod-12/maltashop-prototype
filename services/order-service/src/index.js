import express from 'express';
import { randomUUID } from 'node:crypto';
import { openDb, markProcessed, tx } from './common/db.js';
import { connect, publish, subscribe, isConnected } from './common/mq.js';
import { info, warn } from './common/log.js';
import { buildOrderPlaced, buildOrderOutcome } from './events.js';
import { validateOrderRequest } from './validation.js';

const PORT = Number(process.env.PORT || 3001);
const DB_PATH = process.env.DB_PATH || './data/orders.db';

// Order service owns ONLY this store (database per service).
const db = openDb(
  DB_PATH,
  `CREATE TABLE IF NOT EXISTS orders (
     id            TEXT PRIMARY KEY,
     customer_id   TEXT NOT NULL,
     items         TEXT NOT NULL,
     amount        REAL NOT NULL,
     currency      TEXT NOT NULL DEFAULT 'EUR',
     payment_token TEXT NOT NULL,
     status        TEXT NOT NULL,          -- PENDING | CONFIRMED | CANCELLED
     reason        TEXT,
     correlation_id TEXT NOT NULL,
     idempotency_key TEXT UNIQUE,
     created_at    TEXT NOT NULL,
     updated_at    TEXT NOT NULL
   );`
);

const app = express();
app.use(express.json());

// ---- health endpoints (used by Docker HEALTHCHECK and Kubernetes probes) ----
app.get('/health', (_req, res) => res.json({ status: 'ok' }));            // liveness
app.get('/ready', (_req, res) =>                                          // readiness
  isConnected() ? res.json({ status: 'ready' }) : res.status(503).json({ status: 'broker-unavailable' })
);

// ---- REST endpoint: place an order ----
app.post('/orders', async (req, res) => {
  // The correlation ID is created at the edge (or accepted from the API gateway) and
  // follows the order through every service and every log line.
  const correlationId = req.header('x-correlation-id') || randomUUID();
  const idempotencyKey = req.header('idempotency-key') || null;
  res.setHeader('x-correlation-id', correlationId);

  const errors = validateOrderRequest(req.body);
  if (errors.length) {
    warn('order.rejected', 'invalid order request', correlationId, { errors });
    return res.status(400).json({ errors, correlationId });
  }

  // Idempotent POST: a client retry with the same Idempotency-Key returns the original order.
  if (idempotencyKey) {
    const existing = db.prepare('SELECT * FROM orders WHERE idempotency_key = ?').get(idempotencyKey);
    if (existing) {
      info('order.duplicate_request', 'returning existing order for idempotency key', existing.correlation_id);
      return res.status(200).json({ orderId: existing.id, status: existing.status, correlationId: existing.correlation_id });
    }
  }

  const now = new Date().toISOString();
  const order = {
    id: randomUUID(),
    customer_id: req.body.customerId,
    items: JSON.stringify(req.body.items),
    amount: req.body.amount,
    currency: 'EUR',
    payment_token: req.body.paymentToken,
    status: 'PENDING',
    reason: null,
    correlation_id: correlationId,
    idempotency_key: idempotencyKey,
    created_at: now,
    updated_at: now,
  };
  db.prepare(
    `INSERT INTO orders (id, customer_id, items, amount, currency, payment_token, status, reason, correlation_id, idempotency_key, created_at, updated_at)
     VALUES (@id, @customer_id, @items, @amount, @currency, @payment_token, @status, @reason, @correlation_id, @idempotency_key, @created_at, @updated_at)`
  ).run(order);
  info('order.created', `order ${order.id} saved as PENDING`, correlationId, { orderId: order.id });

  // Asynchronous event. The checkout request does NOT wait for inventory, payment or email.
  // (Limitation: save + publish is not atomic; production would use a transactional outbox.)
  await publish('order.placed', buildOrderPlaced(order), correlationId);

  res.status(202).json({ orderId: order.id, status: order.status, correlationId });
});

app.get('/orders/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM orders WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'order not found' });
  res.json({ ...row, items: JSON.parse(row.items), payment_token: undefined });
});

// ---- saga participant: react to the outcome events of other services ----
function finish(orderId, status, reason, meta) {
  const handler = `order.${meta.routingKey}`;
  const order = tx(db, () => {
    if (!markProcessed(db, meta.messageId, handler)) return null; // duplicate delivery -> ignore
    db.prepare('UPDATE orders SET status = ?, reason = ?, updated_at = ? WHERE id = ? AND status = ?')
      .run(status, reason, new Date().toISOString(), orderId, 'PENDING');
    return db.prepare('SELECT * FROM orders WHERE id = ?').get(orderId);
  });
  return order;
}

async function main() {
  await connect();

  await subscribe('order-service.saga', ['payment.completed', 'payment.failed', 'inventory.failed'], async (payload, meta) => {
    info('event.received', `received ${meta.routingKey}`, meta.correlationId, { orderId: payload.orderId });
    const confirmed = meta.routingKey === 'payment.completed';
    const reason = confirmed ? null : payload.reason || meta.routingKey;
    const order = finish(payload.orderId, confirmed ? 'CONFIRMED' : 'CANCELLED', reason, meta);
    if (!order) {
      info('event.duplicate', `duplicate ${meta.routingKey} ignored (idempotent consumer)`, meta.correlationId);
      return;
    }
    info('order.status_changed', `order ${order.id} is now ${order.status}`, meta.correlationId, { orderId: order.id, status: order.status });
    await publish(confirmed ? 'order.confirmed' : 'order.cancelled', buildOrderOutcome(order, reason), meta.correlationId);
  });

  app.listen(PORT, () => info('service.started', `order-service listening on ${PORT}`));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
