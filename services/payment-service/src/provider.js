import { randomUUID } from 'node:crypto';

// Stand-in for the external payment provider (cards stay with the provider, as the case requires).
// Token "tok_fail" simulates a declined card so the saga's compensation path can be demonstrated.
export async function chargeWithProvider(paymentToken, amount, latencyMs = 150) {
  await new Promise((r) => setTimeout(r, latencyMs)); // simulated network latency
  if (paymentToken === 'tok_fail') return { ok: false, reason: 'card declined by provider' };
  if (amount > 5000) return { ok: false, reason: 'amount exceeds provider limit' };
  return { ok: true, providerRef: `psp_${randomUUID().slice(0, 8)}` };
}
