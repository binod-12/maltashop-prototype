#!/usr/bin/env bash
# End-to-end test of the place-order saga. Used by CI and by you for the report screenshots.
# Usage: bash scripts/smoke-test.sh        (system must already be running)
set -euo pipefail

ORDER=${ORDER_URL:-http://localhost:3001}
INVENTORY=${INVENTORY_URL:-http://localhost:3002}
NOTIFY=${NOTIFICATION_URL:-http://localhost:3004}
fail() { echo "FAIL: $*" >&2; exit 1; }

place() { # place <label> <json> [extra curl args...]
  local label=$1 body=$2; shift 2
  echo ">>> $label" >&2
  curl -s -i -X POST "$ORDER/orders" -H 'content-type: application/json' "$@" -d "$body"
}
field() { sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p" | head -1; }
wait_status() { # wait_status <orderId> <expected>
  for _ in $(seq 1 30); do
    s=$(curl -s "$ORDER/orders/$1" | field status)
    [ "$s" = "$2" ] && return 0
    sleep 1
  done
  fail "order $1 did not reach $2 (last: $s)"
}
stock() { curl -s "$INVENTORY/stock" | sed -n "s/.*\"sku\":\"$1\",\"qty\":\([0-9]*\).*/\1/p" | head -1; }

echo "=== 1. Happy path: order is confirmed ==="
before=$(stock PHONE-X)
resp=$(place "POST /orders (valid)" '{"customerId":"cust-001","items":[{"sku":"PHONE-X","qty":2}],"amount":998,"paymentToken":"tok_ok"}')
echo "$resp" | head -1
id=$(echo "$resp" | field orderId); cid=$(echo "$resp" | field correlationId)
[ -n "$id" ] || fail "no orderId returned"
wait_status "$id" CONFIRMED
[ "$(stock PHONE-X)" -eq $((before - 2)) ] || fail "stock was not reserved"
echo "OK: order $id CONFIRMED, correlationId=$cid"

echo "=== 2. Compensation path: payment declined, stock must be released ==="
before=$(stock LAPTOP-15)
resp=$(place "POST /orders (tok_fail)" '{"customerId":"cust-002","items":[{"sku":"LAPTOP-15","qty":3}],"amount":2700,"paymentToken":"tok_fail"}')
id2=$(echo "$resp" | field orderId)
wait_status "$id2" CANCELLED
sleep 1
[ "$(stock LAPTOP-15)" -eq "$before" ] || fail "stock was not restored by compensation"
echo "OK: order $id2 CANCELLED and LAPTOP-15 stock restored to $before"

echo "=== 3. Out of stock: order is cancelled without charging ==="
resp=$(place "POST /orders (too many)" '{"customerId":"cust-003","items":[{"sku":"LAMP-OAK","qty":99}],"amount":50,"paymentToken":"tok_ok"}')
id3=$(echo "$resp" | field orderId)
wait_status "$id3" CANCELLED
echo "OK: order $id3 CANCELLED (insufficient stock)"

echo "=== 4. Idempotent POST: a retry with the same key returns the same order ==="
key="retry-$(date +%s)"
body='{"customerId":"cust-004","items":[{"sku":"KETTLE-1","qty":1}],"amount":30,"paymentToken":"tok_ok"}'
a=$(place "POST /orders (first)" "$body" -H "idempotency-key: $key" | field orderId)
b=$(place "POST /orders (retry)" "$body" -H "idempotency-key: $key" | field orderId)
[ "$a" = "$b" ] || fail "retry created a second order"
wait_status "$a" CONFIRMED
echo "OK: both requests returned order $a"

echo "=== 5. Notification service received the events ==="
count=$(curl -s "$NOTIFY/notifications" | grep -o "\"order_id\":\"$id\"" | wc -l)
[ "$count" -ge 2 ] || fail "expected received+confirmed emails for $id, found $count"
echo "OK: $count notifications for order $id"

echo; echo "ALL SMOKE TESTS PASSED"
echo "Trace the first order across services with:  docker compose logs | grep $cid"
