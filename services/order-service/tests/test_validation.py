"""UNIT level of the test pyramid: pure logic, no network, no database, runs in milliseconds."""
from app.validation import validate_order_request

GOOD = {"customerId": "c-1", "items": [{"sku": "PHONE-X", "qty": 1}], "amount": 499, "paymentToken": "tok_ok"}


def test_accepts_a_valid_order():
    assert validate_order_request(GOOD) == []


def test_rejects_an_empty_basket():
    assert validate_order_request({**GOOD, "items": []})


def test_rejects_a_non_positive_quantity():
    errs = validate_order_request({**GOOD, "items": [{"sku": "PHONE-X", "qty": 0}]})
    assert "qty" in " ".join(errs)


def test_rejects_a_boolean_quantity():
    assert validate_order_request({**GOOD, "items": [{"sku": "PHONE-X", "qty": True}]})


def test_rejects_a_missing_payment_token():
    assert "paymentToken" in " ".join(validate_order_request({**GOOD, "paymentToken": ""}))


def test_rejects_a_negative_amount():
    assert validate_order_request({**GOOD, "amount": -5})


def test_rejects_a_non_object_body():
    assert validate_order_request(None) == ["body must be a JSON object"]
