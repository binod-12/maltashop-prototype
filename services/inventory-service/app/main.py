import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .common import mq
from .common.contract import validate
from .common.db import mark_processed, open_db, query_all, tx
from .common.log import info, warn
from .stock import release, reserve

PORT = int(os.environ.get("PORT", "3002"))
DB_PATH = os.environ.get("DB_PATH", "./data/inventory.db")
CONTRACT = json.loads((Path(__file__).resolve().parent.parent / "contracts" / "order-placed.consumer.json").read_text())

db = open_db(
    DB_PATH,
    """CREATE TABLE IF NOT EXISTS stock (sku TEXT PRIMARY KEY, qty INTEGER NOT NULL);
       CREATE TABLE IF NOT EXISTS reservations (
         order_id TEXT NOT NULL, sku TEXT NOT NULL, qty INTEGER NOT NULL, status TEXT NOT NULL
       );""",
)
# seed demo stock once
for _sku, _qty in [("LAPTOP-15", 20), ("PHONE-X", 50), ("KETTLE-1", 100), ("LAMP-OAK", 2)]:
    db.execute("INSERT OR IGNORE INTO stock (sku, qty) VALUES (?, ?)", (_sku, _qty))


async def on_order_placed(payload: dict, meta: mq.Meta) -> None:
    """Saga step 1: reserve stock when an order is placed."""
    cid = meta.correlation_id
    info("event.received", "received order.placed", cid, orderId=payload.get("orderId"))

    problems = validate(CONTRACT, payload)
    if problems:
        raise ValueError(f"contract violation: {'; '.join(problems)}")  # -> DLQ

    with tx(db):
        outcome = None
        if mark_processed(db, meta.message_id, "inventory.reserve"):
            outcome = reserve(db, payload["orderId"], payload["items"])
    if outcome is None:  # redelivery
        info("event.duplicate", "duplicate order.placed ignored (idempotent consumer)", cid)
        return

    if outcome["ok"]:
        info("inventory.reserved", f"stock reserved for order {payload['orderId']}", cid)
        await mq.publish("inventory.reserved", {
            "orderId": payload["orderId"], "amount": payload["amount"], "paymentToken": payload["paymentToken"],
        }, cid)
    else:
        warn("inventory.failed", outcome["reason"], cid, orderId=payload["orderId"])
        await mq.publish("inventory.failed", {"orderId": payload["orderId"], "reason": outcome["reason"]}, cid)


async def on_payment_failed(payload: dict, meta: mq.Meta) -> None:
    """Saga compensation: payment failed -> give the stock back."""
    cid = meta.correlation_id
    info("event.received", "received payment.failed", cid, orderId=payload["orderId"])
    with tx(db):
        released = release(db, payload["orderId"]) if mark_processed(db, meta.message_id, "inventory.release") else None
    if released is None:
        info("event.duplicate", "duplicate payment.failed ignored", cid)
        return
    info("inventory.released",
         f"compensation: released {released} reservation line(s) for order {payload['orderId']}", cid)
    await mq.publish("inventory.released", {"orderId": payload["orderId"]}, cid)


async def setup() -> None:
    try:
        await mq.connect()
        await mq.subscribe("inventory-service.order-placed", ["order.placed"], on_order_placed)
        await mq.subscribe("inventory-service.payment-failed", ["payment.failed"], on_payment_failed)
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", flush=True)
        os._exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(setup())
    info("service.started", f"inventory-service listening on {PORT}")
    yield
    task.cancel()
    await mq.close()


app = FastAPI(title="inventory-service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if mq.is_connected():
        return {"status": "ready"}
    return JSONResponse({"status": "broker-unavailable"}, status_code=503)


@app.get("/stock")
async def stock():
    return query_all(db, "SELECT * FROM stock")


@app.get("/reservations")
async def reservations():
    return query_all(db, "SELECT * FROM reservations")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None, access_log=False)
