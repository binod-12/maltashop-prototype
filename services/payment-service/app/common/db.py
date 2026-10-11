"""Each service owns exactly one SQLite file (database-per-service pattern).

sqlite3 ships with Python, so there is no native dependency to install.
All access happens on the event-loop thread and never awaits inside a transaction,
so a single connection per service is safe.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime


def open_db(path: str, schema_sql: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)  # autocommit; we BEGIN explicitly
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(schema_sql)
    db.execute(
        """CREATE TABLE IF NOT EXISTS processed_events (
             message_id   TEXT NOT NULL,
             handler      TEXT NOT NULL,
             processed_at TEXT NOT NULL,
             PRIMARY KEY (message_id, handler)
           )"""
    )
    return db


def mark_processed(db: sqlite3.Connection, message_id: str, handler: str) -> bool:
    """Idempotent consumer: True the first time a (message_id, handler) pair is seen, False on a
    redelivery. Call it inside the same transaction as the business change."""
    cur = db.execute(
        "INSERT OR IGNORE INTO processed_events (message_id, handler, processed_at) VALUES (?, ?, ?)",
        (message_id, handler, datetime.now(UTC).isoformat()),
    )
    return cur.rowcount == 1


@contextmanager
def tx(db: sqlite3.Connection):
    """BEGIN ... COMMIT, or ROLLBACK if the block raises."""
    db.execute("BEGIN")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def query_all(db: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def query_one(db: sqlite3.Connection, sql: str, params=()):
    row = db.execute(sql, params).fetchone()
    return dict(row) if row else None
