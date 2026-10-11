"""Pure stock logic, kept separate from I/O so it is easy to unit test.

reserve() is all-or-nothing: either every line is reserved or nothing changes.
"""


def reserve(db, order_id: str, items: list[dict]) -> dict:
    for it in items:
        row = db.execute("SELECT qty FROM stock WHERE sku = ?", (it["sku"],)).fetchone()
        if row is None:
            return {"ok": False, "reason": f"unknown SKU {it['sku']}"}
        if row["qty"] < it["qty"]:
            return {"ok": False, "reason": f"insufficient stock for {it['sku']}"}
    for it in items:
        db.execute("UPDATE stock SET qty = qty - ? WHERE sku = ?", (it["qty"], it["sku"]))
        db.execute("INSERT INTO reservations (order_id, sku, qty, status) VALUES (?, ?, ?, ?)",
                   (order_id, it["sku"], it["qty"], "RESERVED"))
    return {"ok": True}


def release(db, order_id: str) -> int:
    """Compensating action for a failed payment: put the reserved quantities back."""
    rows = db.execute("SELECT sku, qty FROM reservations WHERE order_id = ? AND status = 'RESERVED'",
                      (order_id,)).fetchall()
    for r in rows:
        db.execute("UPDATE stock SET qty = qty + ? WHERE sku = ?", (r["qty"], r["sku"]))
    db.execute("UPDATE reservations SET status = 'RELEASED' WHERE order_id = ? AND status = 'RESERVED'", (order_id,))
    return len(rows)
