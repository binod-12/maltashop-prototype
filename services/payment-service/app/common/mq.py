"""RabbitMQ helper built on aio-pika.

Topic exchange, durable queues, persistent messages, publisher confirms, manual acks,
a dead-letter queue, and correlation ID propagation through message properties.
"""
import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import aio_pika

from .log import error, info, warn

URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
EXCHANGE = "maltashop.events"
DLX = "maltashop.dlx"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None


@dataclass
class Meta:
    correlation_id: str | None
    message_id: str | None
    routing_key: str


def _on_close(_sender, exc=None):
    # A clean shutdown passes no exception. An unexpected drop exits the process so the
    # orchestrator (Compose restart policy / Kubernetes) starts a fresh, healthy one (12-factor IX).
    if exc is not None:
        error("mq.connection_closed", f"connection lost ({exc}); exiting so the orchestrator restarts us")
        os._exit(1)


async def connect(retries: int = 30) -> None:
    global _connection, _channel, _exchange
    for attempt in range(1, retries + 1):
        try:
            _connection = await aio_pika.connect(URL)
            _connection.close_callbacks.add(_on_close)
            _channel = await _connection.channel(publisher_confirms=True)
            _exchange = await _channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
            await _channel.declare_exchange(DLX, aio_pika.ExchangeType.DIRECT, durable=True)
            info("mq.connected", "connected to RabbitMQ")
            return
        except Exception as exc:  # noqa: BLE001 - any failure means "broker not ready yet"
            warn("mq.retry", f"broker not ready (attempt {attempt}/{retries}): {exc}")
            await asyncio.sleep(2)
    raise RuntimeError("could not connect to RabbitMQ")


async def publish(routing_key: str, payload: dict, correlation_id: str | None, message_id: str | None = None) -> str:
    """Publish an event and wait for the broker's confirm. message_id is what consumers use for idempotency."""
    message_id = message_id or str(uuid.uuid4())
    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=message_id,
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        type=routing_key,
    )
    await _exchange.publish(message, routing_key=routing_key)
    info("event.published", f"published {routing_key}", correlation_id, routingKey=routing_key, messageId=message_id)
    return message_id


async def subscribe(queue_name: str, routing_keys: list[str], handler) -> None:
    """Subscribe a durable queue to one or more routing keys.

    handler(payload, meta) is awaited for every message. Raising sends the message to the DLQ.
    """
    channel = await _connection.channel()
    await channel.set_qos(prefetch_count=10)

    # Each queue dead-letters to its OWN .dlq: direct exchange, routing key = the dlq name.
    dlq_name = f"{queue_name}.dlq"
    dlx = await channel.declare_exchange(DLX, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(dlq_name, durable=True)
    await dlq.bind(dlx, routing_key=dlq_name)

    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": dlq_name},
    )
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    for key in routing_keys:
        await queue.bind(exchange, routing_key=key)

    async def on_message(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
        meta = Meta(msg.correlation_id, msg.message_id, msg.routing_key or "")
        try:
            payload = json.loads(msg.body.decode())
            await handler(payload, meta)
            await msg.ack()
        except Exception as exc:  # noqa: BLE001
            error(
                "event.handler_failed",
                f"{meta.routing_key} failed: {exc}",
                meta.correlation_id,
                routingKey=meta.routing_key,
                messageId=meta.message_id,
            )
            await msg.nack(requeue=False)  # -> dead-letter queue

    await queue.consume(on_message)
    info("mq.subscribed", f"queue {queue_name} bound to {', '.join(routing_keys)}")


def is_connected() -> bool:
    return bool(_connection and not _connection.is_closed and _exchange is not None)


async def close() -> None:
    if _connection and not _connection.is_closed:
        await _connection.close()
