"""Stand-in for the external payment provider (cards stay with the provider, as the case requires).

Token "tok_fail" simulates a declined card so the saga's compensation path can be demonstrated.
"""
import asyncio
import uuid


async def charge_with_provider(payment_token: str, amount: float, latency_ms: int = 150) -> dict:
    await asyncio.sleep(latency_ms / 1000)  # simulated network latency
    if payment_token == "tok_fail":
        return {"ok": False, "reason": "card declined by provider"}
    if amount > 5000:
        return {"ok": False, "reason": "amount exceeds provider limit"}
    return {"ok": True, "provider_ref": f"psp_{uuid.uuid4().hex[:8]}"}
