import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TEMPLATES } from '../src/templates.js';

test('every saga outcome has a customer message', () => {
  for (const key of ['order.placed', 'order.confirmed', 'order.cancelled']) assert.equal(typeof TEMPLATES[key], 'function');
});
test('cancellation message includes the reason', () => {
  assert.match(TEMPLATES['order.cancelled']({ orderId: 'o1', reason: 'card declined by provider' }), /card declined/);
});
