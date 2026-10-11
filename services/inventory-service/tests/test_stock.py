"""UNIT level with an in-memory database: proves reservation is all-or-nothing and that
the compensating action (release) restores stock exactly."""
import sqlite3

import pytest
from app.stock import release, reserve


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE stock (sku TEXT PRIMARY KEY, qty INTEGER NOT NULL);
           CREATE TABLE reservations (order_id TEXT, sku TEXT, qty INTEGER, status TEXT);
           INSERT INTO stock VALUES ('A', 5), ('B', 1);"""
    )
    return conn


def qty(db, sku):
    return db.execute("SELECT qty FROM stock WHERE sku = ?", (sku,)).fetchone()["qty"]


def test_reserves_stock_when_every_line_is_available(db):
    assert reserve(db, "o1", [{"sku": "A", "qty": 2}])["ok"] is True
    assert qty(db, "A") == 3


def test_is_all_or_nothing(db):
    r = reserve(db, "o1", [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 5}])
    assert r["ok"] is False
    assert qty(db, "A") == 5


def test_rejects_unknown_skus(db):
    assert reserve(db, "o1", [{"sku": "ZZZ", "qty": 1}])["ok"] is False


def test_compensation_release_restores_quantity_and_is_safe_to_repeat(db):
    reserve(db, "o1", [{"sku": "A", "qty": 4}])
    assert release(db, "o1") == 1
    assert qty(db, "A") == 5
    assert release(db, "o1") == 0
    assert qty(db, "A") == 5
