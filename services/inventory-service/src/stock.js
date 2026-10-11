// Pure stock logic, kept separate from I/O so it is easy to unit test.
// reserve() is all-or-nothing: either every line is reserved or nothing changes.
export function reserve(db, orderId, items) {
  const getStock = db.prepare('SELECT qty FROM stock WHERE sku = ?');
  for (const it of items) {
    const row = getStock.get(it.sku);
    if (!row) return { ok: false, reason: `unknown SKU ${it.sku}` };
    if (row.qty < it.qty) return { ok: false, reason: `insufficient stock for ${it.sku}` };
  }
  const dec = db.prepare('UPDATE stock SET qty = qty - ? WHERE sku = ?');
  const rec = db.prepare('INSERT INTO reservations (order_id, sku, qty, status) VALUES (?, ?, ?, ?)');
  for (const it of items) {
    dec.run(it.qty, it.sku);
    rec.run(orderId, it.sku, it.qty, 'RESERVED');
  }
  return { ok: true };
}

// Compensating action for a failed payment: put the reserved quantities back.
export function release(db, orderId) {
  const rows = db.prepare("SELECT sku, qty FROM reservations WHERE order_id = ? AND status = 'RESERVED'").all(orderId);
  const inc = db.prepare('UPDATE stock SET qty = qty + ? WHERE sku = ?');
  for (const r of rows) inc.run(r.qty, r.sku);
  db.prepare("UPDATE reservations SET status = 'RELEASED' WHERE order_id = ? AND status = 'RESERVED'").run(orderId);
  return rows.length;
}
