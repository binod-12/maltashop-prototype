"""CONTRACT level of the test pyramid (report section 3.2).

Consumer-driven: the Inventory service owns a file saying what it needs from order.placed.
This test (run in CI) proves the Order service still produces an event that satisfies it,
so a breaking change fails the build before deployment.

Run from the repo root:  python -m pytest contract-tests
"""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVICES = ROOT / "services"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


events = _load("order_events", SERVICES / "order-service/app/events.py")
contract_lib = _load("contract_lib", SERVICES / "inventory-service/app/common/contract.py")
CONTRACT = json.loads((SERVICES / "inventory-service/contracts/order-placed.consumer.json").read_text())

DB_ROW = {
    "id": "o-1", "customer_id": "c-1", "items": json.dumps([{"sku": "PHONE-X", "qty": 2}]),
    "amount": 998, "currency": "EUR", "payment_token": "tok_ok",
}


def test_order_placed_satisfies_the_inventory_consumer_contract():
    assert contract_lib.validate(CONTRACT, events.build_order_placed(DB_ROW)) == []


def test_a_breaking_change_renaming_amount_is_caught():
    event = events.build_order_placed(DB_ROW)
    event["total"] = event.pop("amount")
    problems = contract_lib.validate(CONTRACT, event)
    assert any("amount" in p for p in problems), problems


def test_a_wrong_type_qty_as_string_is_caught():
    row = {**DB_ROW, "items": json.dumps([{"sku": "PHONE-X", "qty": "2"}])}
    assert contract_lib.validate(CONTRACT, events.build_order_placed(row))
