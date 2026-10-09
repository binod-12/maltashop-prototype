// UNIT level of the test pyramid: pure logic, no network, no database, runs in milliseconds.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateOrderRequest } from '../src/validation.js';

const good = { customerId: 'c-1', items: [{ sku: 'PHONE-X', qty: 1 }], amount: 499, paymentToken: 'tok_ok' };

test('accepts a valid order', () => {
  assert.deepEqual(validateOrderRequest(good), []);
});

test('rejects an empty basket', () => {
  assert.ok(validateOrderRequest({ ...good, items: [] }).length > 0);
});

test('rejects a non-positive quantity', () => {
  const errs = validateOrderRequest({ ...good, items: [{ sku: 'PHONE-X', qty: 0 }] });
  assert.match(errs.join(' '), /qty/);
});

test('rejects a missing payment token (cards never reach this service)', () => {
  assert.match(validateOrderRequest({ ...good, paymentToken: '' }).join(' '), /paymentToken/);
});

test('rejects a negative amount', () => {
  assert.ok(validateOrderRequest({ ...good, amount: -5 }).length > 0);
});
