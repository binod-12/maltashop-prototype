// UNIT level with an in-memory database: proves reservation is all-or-nothing and that
// the compensating action (release) restores stock exactly.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { reserve, release } from '../src/stock.js';

function freshDb() {
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE stock (sku TEXT PRIMARY KEY, qty INTEGER NOT NULL);
           CREATE TABLE reservations (order_id TEXT, sku TEXT, qty INTEGER, status TEXT);
           INSERT INTO stock VALUES ('A', 5), ('B', 1);`);
  return db;
}
const qty = (db, sku) => db.prepare('SELECT qty FROM stock WHERE sku = ?').get(sku).qty;

test('reserves stock when every line is available', () => {
  const db = freshDb();
  assert.equal(reserve(db, 'o1', [{ sku: 'A', qty: 2 }]).ok, true);
  assert.equal(qty(db, 'A'), 3);
});

test('is all-or-nothing: one short line means nothing is reserved', () => {
  const db = freshDb();
  const r = reserve(db, 'o1', [{ sku: 'A', qty: 2 }, { sku: 'B', qty: 5 }]);
  assert.equal(r.ok, false);
  assert.equal(qty(db, 'A'), 5);
});

test('rejects unknown SKUs', () => {
  assert.equal(reserve(freshDb(), 'o1', [{ sku: 'ZZZ', qty: 1 }]).ok, false);
});

test('compensation: release restores the original quantity and is safe to repeat', () => {
  const db = freshDb();
  reserve(db, 'o1', [{ sku: 'A', qty: 4 }]);
  assert.equal(release(db, 'o1'), 1);
  assert.equal(qty(db, 'A'), 5);
  assert.equal(release(db, 'o1'), 0); // second call does nothing
  assert.equal(qty(db, 'A'), 5);
});
