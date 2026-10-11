// CONTRACT level of the test pyramid (report section 3.2).
// Consumer-driven: the Inventory service owns a file saying what it needs from order.placed.
// This test (run in CI for the Order service) proves the Order service still produces an
// event that satisfies it - so a breaking change fails the build before deployment.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildOrderPlaced } from '../services/order-service/src/events.js';
import { validate } from '../services/inventory-service/src/common/contract.js';

const contract = JSON.parse(
  readFileSync(new URL('../services/inventory-service/contracts/order-placed.consumer.json', import.meta.url))
);

const dbRow = {
  id: 'o-1', customer_id: 'c-1', items: JSON.stringify([{ sku: 'PHONE-X', qty: 2 }]),
  amount: 998, currency: 'EUR', payment_token: 'tok_ok',
};

test('Order service order.placed satisfies the Inventory consumer contract', () => {
  assert.deepEqual(validate(contract, buildOrderPlaced(dbRow)), []);
});

test('a breaking change (renaming amount) is caught by the contract', () => {
  const event = buildOrderPlaced(dbRow);
  event.total = event.amount;
  delete event.amount;
  const problems = validate(contract, event);
  assert.ok(problems.some((p) => p.includes('amount')), problems.join('; '));
});

test('a wrong type (qty as string) is caught by the contract', () => {
  const event = buildOrderPlaced({ ...dbRow, items: JSON.stringify([{ sku: 'PHONE-X', qty: '2' }]) });
  assert.ok(validate(contract, event).length > 0);
});
