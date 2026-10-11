import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chargeWithProvider } from '../src/provider.js';

test('a normal token is charged and returns a provider reference', async () => {
  const r = await chargeWithProvider('tok_ok', 100, 0);
  assert.equal(r.ok, true);
  assert.match(r.providerRef, /^psp_/);
});
test('tok_fail simulates a declined card (drives the compensation path)', async () => {
  const r = await chargeWithProvider('tok_fail', 100, 0);
  assert.equal(r.ok, false);
});
test('amounts above the provider limit are refused', async () => {
  assert.equal((await chargeWithProvider('tok_ok', 9000, 0)).ok, false);
});
