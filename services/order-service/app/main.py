import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .common import mq
from .common.db import mark_processed, open_db, query_one, tx
from .common.log import info, warn
from .events import build_order_outcome, build_order_placed
from .validation import validate_order_request

PORT = int(os.environ.get("PORT", "3001"))
DB_PATH = os.environ.get("DB_PATH", "./data/orders.db")

# Order service owns ONLY this store (database per service).
db = open_db(
    DB_PATH,
    """CREATE TABLE IF NOT EXISTS orders (
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
       );""",
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def finish(order_id: str, status: str, reason, meta: mq.Meta):
    """Apply a saga outcome to the order. Returns None for a duplicate delivery."""
    handler = f"order.{meta.routing_key}"
    with tx(db):
        if not mark_processed(db, meta.message_id, handler):
            return None  # duplicate delivery -> ignore
        db.execute(
            "UPDATE orders SET status = ?, reason = ?, updated_at = ? WHERE id = ? AND status = ?",
            (status, reason, _now(), order_id, "PENDING"),
        )
        return query_one(db, "SELECT * FROM orders WHERE id = ?", (order_id,))


async def on_saga_event(payload: dict, meta: mq.Meta) -> None:
    info("event.received", f"received {meta.routing_key}", meta.correlation_id, orderId=payload["orderId"])
    confirmed = meta.routing_key == "payment.completed"
    reason = None if confirmed else payload.get("reason") or meta.routing_key
    order = finish(payload["orderId"], "CONFIRMED" if confirmed else "CANCELLED", reason, meta)
    if order is None:
        info("event.duplicate", f"duplicate {meta.routing_key} ignored (idempotent consumer)", meta.correlation_id)
        return
    info("order.status_changed", f"order {order['id']} is now {order['status']}", meta.correlation_id,
         orderId=order["id"], status=order["status"])
    await mq.publish("order.confirmed" if confirmed else "order.cancelled",
                     build_order_outcome(order, reason), meta.correlation_id)


async def setup() -> None:
    try:
        await mq.connect()
        await mq.subscribe("order-service.saga", ["payment.completed", "payment.failed", "inventory.failed"], on_saga_event)
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", flush=True)
        os._exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(setup())
    info("service.started", f"order-service listening on {PORT}")
    yield
    task.cancel()
    await mq.close()


app = FastAPI(title="order-service", lifespan=lifespan)


@app.get("/health")
async def health():  # liveness
    return {"status": "ok"}


@app.get("/ready")
async def ready():  # readiness
    if mq.is_connected():
        return {"status": "ready"}
    return JSONResponse({"status": "broker-unavailable"}, status_code=503)


@app.post("/orders")
async def place_order(request: Request):
    # The correlation ID is created at the edge (or accepted from the API gateway) and
    # follows the order through every service and every log line.
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    idempotency_key = request.headers.get("idempotency-key") or None
    headers = {"x-correlation-id": correlation_id}

    try:
        body = await request.json()
    except ValueError:
        body = None
    errors = validate_order_request(body)
    if errors:
        warn("order.rejected", "invalid order request", correlation_id, errors=errors)
        return JSONResponse({"errors": errors, "correlationId": correlation_id}, status_code=400, headers=headers)

    # Idempotent POST: a client retry with the same Idempotency-Key returns the original order.
    if idempotency_key:
        existing = query_one(db, "SELECT * FROM orders WHERE idempotency_key = ?", (idempotency_key,))
        if existing:
            info("order.duplicate_request", "returning existing order for idempotency key", existing["correlation_id"])
            return JSONResponse(
                {"orderId": existing["id"], "status": existing["status"], "correlationId": existing["correlation_id"]},
                status_code=200, headers=headers)

    now = _now()
    order = {
        "id": str(uuid.uuid4()), "customer_id": body["customerId"], "items": json.dumps(body["items"]),
        "amount": body["amount"], "currency": "EUR", "payment_token": body["paymentToken"],
        "status": "PENDING", "reason": None, "correlation_id": correlation_id,
        "idempotency_key": idempotency_key, "created_at": now, "updated_at": now,
    }
    db.execute(
        """INSERT INTO orders (id, customer_id, items, amount, currency, payment_token, status, reason,
                               correlation_id, idempotency_key, created_at, updated_at)
           VALUES (:id, :customer_id, :items, :amount, :currency, :payment_token, :status, :reason,
                   :correlation_id, :idempotency_key, :created_at, :updated_at)""",
        order,
    )
    info("order.created", f"order {order['id']} saved as PENDING", correlation_id, orderId=order["id"])

    # Asynchronous event. The checkout request does NOT wait for inventory, payment or email.
    # (Limitation: save + publish is not atomic; production would use a transactional outbox.)
    await mq.publish("order.placed", build_order_placed(order), correlation_id)

    return JSONResponse({"orderId": order["id"], "status": order["status"], "correlationId": correlation_id},
                        status_code=202, headers=headers)


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    row = query_one(db, "SELECT * FROM orders WHERE id = ?", (order_id,))
    if not row:
        return JSONResponse({"error": "order not found"}, status_code=404)
    row["items"] = json.loads(row["items"])
    row.pop("payment_token", None)
    return row


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None, access_log=False)
