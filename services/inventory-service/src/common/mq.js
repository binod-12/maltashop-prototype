// RabbitMQ helper: topic exchange, durable queues, persistent messages, publisher confirms,
// manual acks, a dead-letter queue and correlation ID propagation through message headers.
import amqp from 'amqplib';
import { randomUUID } from 'node:crypto';
import { info, warn, error } from './log.js';

const URL = process.env.RABBITMQ_URL || 'amqp://guest:guest@localhost:5672';
export const EXCHANGE = 'maltashop.events';
const DLX = 'maltashop.dlx';

let conn;
let pubChannel;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export async function connect(retries = 30) {
  for (let i = 1; i <= retries; i++) {
    try {
      conn = await amqp.connect(URL);
      conn.on('error', (e) => error('mq.connection_error', e.message));
      conn.on('close', () => {
        error('mq.connection_closed', 'connection closed, exiting so the orchestrator restarts us');
        process.exit(1);
      });
      pubChannel = await conn.createConfirmChannel();
      await pubChannel.assertExchange(EXCHANGE, 'topic', { durable: true });
      await pubChannel.assertExchange(DLX, 'fanout', { durable: true });
      info('mq.connected', 'connected to RabbitMQ');
      return;
    } catch (e) {
      warn('mq.retry', `broker not ready (attempt ${i}/${retries}): ${e.message}`);
      await sleep(2000);
    }
  }
  throw new Error('could not connect to RabbitMQ');
}

// Publish an event. messageId is what consumers use for idempotency.
export async function publish(routingKey, payload, correlationId, messageId = randomUUID()) {
  const body = Buffer.from(JSON.stringify(payload));
  await new Promise((resolve, reject) => {
    pubChannel.publish(
      EXCHANGE,
      routingKey,
      body,
      {
        persistent: true,
        contentType: 'application/json',
        messageId,
        correlationId,
        timestamp: Date.now(),
        type: routingKey,
      },
      (err) => (err ? reject(err) : resolve())
    );
  });
  info('event.published', `published ${routingKey}`, correlationId, { routingKey, messageId });
  return messageId;
}

// Subscribe a durable queue to one or more routing keys. The handler receives
// (payload, { correlationId, messageId, routingKey }). Throwing sends the message to the DLQ.
export async function subscribe(queueName, routingKeys, handler) {
  const ch = await conn.createChannel();
  await ch.assertQueue(`${queueName}.dlq`, { durable: true });
  await ch.bindQueue(`${queueName}.dlq`, DLX, '');
  await ch.assertQueue(queueName, {
    durable: true,
    arguments: { 'x-dead-letter-exchange': DLX },
  });
  for (const key of routingKeys) await ch.bindQueue(queueName, EXCHANGE, key);
  await ch.prefetch(10);

  await ch.consume(queueName, async (msg) => {
    if (!msg) return;
    const meta = {
      correlationId: msg.properties.correlationId,
      messageId: msg.properties.messageId,
      routingKey: msg.fields.routingKey,
    };
    try {
      const payload = JSON.parse(msg.content.toString());
      await handler(payload, meta);
      ch.ack(msg);
    } catch (e) {
      error('event.handler_failed', `${meta.routingKey} failed: ${e.message}`, meta.correlationId, meta);
      ch.nack(msg, false, false); // -> dead-letter queue
    }
  });
  info('mq.subscribed', `queue ${queueName} bound to ${routingKeys.join(', ')}`);
}

export function isConnected() {
  return Boolean(conn && pubChannel);
}
