import http from 'node:http';
import { openDb, markProcessed, tx } from './common/db.js';
import { connect, subscribe, isConnected } from './common/mq.js';
import { info } from './common/log.js';
import { TEMPLATES } from './templates.js';

const PORT = Number(process.env.PORT || 3004);
const DB_PATH = process.env.DB_PATH || './data/notifications.db';

const db = openDb(
  DB_PATH,
  `CREATE TABLE IF NOT EXISTS notifications (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     order_id TEXT NOT NULL,
     kind TEXT NOT NULL,
     body TEXT NOT NULL,
     correlation_id TEXT,
     sent_at TEXT NOT NULL
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
    if (req.url.startsWith('/notifications')) return res.end(JSON.stringify(db.prepare('SELECT * FROM notifications ORDER BY id').all()));
    res.statusCode = 404;
    res.end('{}');
  })
  .listen(PORT, () => info('service.started', `notification-service listening on ${PORT}`));

async function main() {
  await connect();

  // Notification is a pure subscriber. If it is slow or crashes, checkout is unaffected:
  // messages simply wait in its durable queue (the March memory-leak incident cannot recur this way).
  await subscribe('notification-service.events', ['order.placed', 'order.confirmed', 'order.cancelled'], async (payload, meta) => {
    const { correlationId } = meta;
    info('event.received', `received ${meta.routingKey}`, correlationId, { orderId: payload.orderId });

    const fresh = tx(db, () => markProcessed(db, meta.messageId, `notify.${meta.routingKey}`));
    if (!fresh) return info('event.duplicate', 'duplicate event ignored - no second email', correlationId);

    const body = TEMPLATES[meta.routingKey](payload);
    db.prepare('INSERT INTO notifications (order_id, kind, body, correlation_id, sent_at) VALUES (?, ?, ?, ?, ?)')
      .run(payload.orderId, meta.routingKey, body, correlationId, new Date().toISOString());
    info('notification.sent', `EMAIL (simulated): ${body}`, correlationId, { orderId: payload.orderId });
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
