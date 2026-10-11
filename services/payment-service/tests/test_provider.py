from app.provider import charge_with_provider


async def test_normal_token_is_charged_and_returns_a_reference():
    r = await charge_with_provider("tok_ok", 100, 0)
    assert r["ok"] is True
    assert r["provider_ref"].startswith("psp_")


async def test_tok_fail_simulates_a_declined_card():
    assert (await charge_with_provider("tok_fail", 100, 0))["ok"] is False


async def test_amounts_above_the_provider_limit_are_refused():
    assert (await charge_with_provider("tok_ok", 9000, 0))["ok"] is False
