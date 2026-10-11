from app.templates import TEMPLATES


def test_every_saga_outcome_has_a_customer_message():
    for key in ("order.placed", "order.confirmed", "order.cancelled"):
        assert callable(TEMPLATES[key])


def test_cancellation_message_includes_the_reason():
    assert "card declined" in TEMPLATES["order.cancelled"]({"orderId": "o1", "reason": "card declined by provider"})


def test_cancellation_without_reason_has_a_fallback():
    assert "unknown reason" in TEMPLATES["order.cancelled"]({"orderId": "o1"})
