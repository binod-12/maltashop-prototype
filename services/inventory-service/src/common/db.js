// Each service owns exactly one SQLite file (database-per-service pattern).
// node:sqlite is built into Node 22, so there is no native dependency to compile.
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export function openDb(path, schemaSql) {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec('PRAGMA journal_mode = WAL;');
  db.exec(schemaSql);
  db.exec(`CREATE TABLE IF NOT EXISTS processed_events (
    message_id TEXT NOT NULL,
    handler    TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (message_id, handler)
  );`);
  return db;
}

// Idempotent consumer: returns true the first time a (messageId, handler) pair is seen,
// false on a redelivery. Call inside the same transaction as the business change.
export function markProcessed(db, messageId, handler) {
  const res = db
    .prepare('INSERT OR IGNORE INTO processed_events (message_id, handler, processed_at) VALUES (?, ?, ?)')
    .run(messageId, handler, new Date().toISOString());
  return res.changes === 1;
}

export function tx(db, fn) {
  db.exec('BEGIN');
  try {
    const out = fn();
    db.exec('COMMIT');
    return out;
  } catch (e) {
    db.exec('ROLLBACK');
    throw e;
  }
}
