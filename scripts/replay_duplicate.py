"""Demonstrates idempotent consumers (report 6.1): re-publish an order.placed event with the SAME
message id, as RabbitMQ would on a redelivery after a consumer crash. Nothing should happen twice.

Usage: python scripts/replay_duplicate.py <orderId> <messageId> <correlationId>
Needs the packages from services/order-service/requirements.txt (aio-pika, httpx via requirements-dev).
"""
import asyncio
import json
import os
import sys
import urllib.request

import aio_pika


async def main(order_id: str, message_id: str, correlation_id: str) -> None:
    url = os.environ.get("RABBITMQ_URL", "amqp://maltashop:maltashop_dev@localhost:5672")
    order_url = os.environ.get("ORDER_URL", "http://localhost:3001")
    with urllib.request.urlopen(f"{order_url}/orders/{order_id}") as resp:  # noqa: S310 - local URL
        order = json.load(resp)

    payload = {
        "orderId": order["id"], "customerId": order["customer_id"], "items": order["items"],
        "amount": order["amount"], "currency": order["currency"], "paymentToken": "tok_ok",
    }
    conn = await aio_pika.connect(url)
    async with conn:
        channel = await conn.channel(publisher_confirms=True)
        exchange = await channel.get_exchange("maltashop.events")
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_id, correlation_id=correlation_id, content_type="application/json"),
            routing_key="order.placed",
        )
    print(f"re-published order.placed for {order_id} with the same messageId {message_id}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python scripts/replay_duplicate.py <orderId> <messageId> <correlationId>")
    asyncio.run(main(*sys.argv[1:4]))
