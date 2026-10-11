import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .common import mq
from .common.db import mark_processed, open_db, query_all, tx
from .common.log import info, warn
from .provider import charge_with_provider

PORT = int(os.environ.get("PORT", "3003"))
DB_PATH = os.environ.get("DB_PATH", "./data/payments.db")

db = open_db(
    DB_PATH,
    """CREATE TABLE IF NOT EXISTS payments (
         id TEXT PRIMARY KEY,
         order_id TEXT NOT NULL UNIQUE,      -- one payment per order = natural idempotency key
         amount REAL NOT NULL,
         status TEXT NOT NULL,               -- COMPLETED | FAILED
         provider_ref TEXT,
         created_at TEXT NOT NULL
       );""",
)


async def on_inventory_reserved(payload: dict, meta: mq.Meta) -> None:
    """Saga step 2: stock is reserved -> take payment."""
    cid = meta.correlation_id
    info("event.received", "received inventory.reserved", cid, orderId=payload["orderId"])

    # Idempotency: if we already handled this message, do not charge twice.
    with tx(db):
        seen = not mark_processed(db, meta.message_id, "payment.charge")
    if seen:
        info("event.duplicate", "duplicate inventory.reserved ignored - no double charge", cid)
        return

    result = await charge_with_provider(payload["paymentToken"], payload["amount"])
    pid = str(uuid.uuid4())
    db.execute(
        "INSERT OR IGNORE INTO payments (id, order_id, amount, status, provider_ref, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, payload["orderId"], payload["amount"], "COMPLETED" if result["ok"] else "FAILED",
         result.get("provider_ref"), datetime.now(UTC).isoformat()),
    )

    if result["ok"]:
        info("payment.completed", f"payment {pid} completed for order {payload['orderId']}", cid)
        await mq.publish("payment.completed",
                         {"orderId": payload["orderId"], "paymentId": pid, "amount": payload["amount"]}, cid)
    else:
        warn("payment.failed", result["reason"], cid, orderId=payload["orderId"])
        await mq.publish("payment.failed", {"orderId": payload["orderId"], "reason": result["reason"]}, cid)


async def setup() -> None:
    try:
        await mq.connect()
        await mq.subscribe("payment-service.inventory-reserved", ["inventory.reserved"], on_inventory_reserved)
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", flush=True)
        os._exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(setup())
    info("service.started", f"payment-service listening on {PORT}")
    yield
    task.cancel()
    await mq.close()


app = FastAPI(title="payment-service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if mq.is_connected():
        return {"status": "ready"}
    return JSONResponse({"status": "broker-unavailable"}, status_code=503)


@app.get("/payments")
async def payments():
    return query_all(db, "SELECT * FROM payments")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None, access_log=False)
