"""Demonstrates the dead-letter queue: publish a malformed order.placed event.

Inventory rejects it (contract violation) and RabbitMQ moves it to
inventory-service.order-placed.dlq instead of retrying it forever.

Usage: python scripts/send_poison_message.py
"""
import asyncio
import json
import os

import aio_pika


async def main() -> None:
    url = os.environ.get("RABBITMQ_URL", "amqp://maltashop:maltashop_dev@localhost:5672")
    conn = await aio_pika.connect(url)
    async with conn:
        channel = await conn.channel(publisher_confirms=True)
        exchange = await channel.get_exchange("maltashop.events")
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps({"orderId": "bad-order"}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id="poison-message-1",
                correlation_id="poison-demo",
                content_type="application/json",
            ),
            routing_key="order.placed",
        )
    print("published a malformed order.placed event (correlationId poison-demo)")


if __name__ == "__main__":
    asyncio.run(main())
