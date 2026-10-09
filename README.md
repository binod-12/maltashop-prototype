# MaltaShop – "Place an Order" Prototype

Prototype for **Unit 5: Service-Oriented Architecture and Microservices Fundamentals** (Learn Key Institute, Malta Campus).
It implements the *place an order* flow of the fictional MaltaShop Ltd platform as four small services that
communicate through a message broker and keep an order consistent **without a distributed database transaction**
(a choreography-based saga with compensation).

## What the system is

| Service | Port | Responsibility | Owns (own data store) |
|---|---|---|---|
| `order-service` | 3001 | REST API `POST /orders`; tracks order status; confirms or cancels it based on saga outcome | `orders` (SQLite file on its own volume) |
| `inventory-service` | 3002 | Reserves stock; **releases it** if payment fails (compensating action) | `stock`, `reservations` |
| `payment-service` | 3003 | Charges via a simulated external payment provider (only a payment *token* ever enters the system) | `payments` |
| `notification-service` | 3004 | Sends (simulated) customer emails. Pure subscriber – it can fail without affecting checkout | `notifications` |
| `rabbitmq` | 5672 / 15672 | Message broker (topic exchange `maltashop.events`, durable queues, dead-letter queue) | broker volume |

### Saga (choreography)

```
POST /orders ─► order-service ── order.placed ──► inventory-service ── inventory.reserved ──► payment-service
                     ▲  (PENDING)        │                 │ inventory.failed                    │
                     │                   └──► notification  │                                     ├─ payment.completed ─► order-service ─ order.confirmed ─► notification
                     │                                      │                                     └─ payment.failed ──┬─► order-service ─ order.cancelled ─► notification
                     └──────────────────────────────────────┴─────────────────────────────────────────────────────────└─► inventory-service (RELEASE stock = compensation)
```

Key properties: every service owns its data; every consumer is **idempotent** (`processed_events` table keyed by
`messageId`); every log line is **structured JSON carrying a `correlationId`** that follows an order through all services;
poison messages go to a **dead-letter queue**; the checkout request returns `202 Accepted` immediately and never waits
for inventory, payment or email.

## Run it

Prerequisites: Docker Desktop (or Docker Engine) with the Compose plugin. Nothing else is needed.

```bash
cp .env.example .env          # optional – defaults already work
docker compose up --build     # builds 4 images, starts broker + services
```

Wait until all services show `healthy` (`docker compose ps`), then in another terminal:

```bash
bash scripts/smoke-test.sh    # happy path, compensation path, out-of-stock, idempotent retry
```

Or by hand:

```bash
curl -i -X POST http://localhost:3001/orders -H 'content-type: application/json' \
  -d '{"customerId":"cust-001","items":[{"sku":"PHONE-X","qty":2}],"amount":998,"paymentToken":"tok_ok"}'
# -> 202 {"orderId":"…","status":"PENDING","correlationId":"…"}

curl http://localhost:3001/orders/<orderId>        # CONFIRMED a moment later
curl http://localhost:3004/notifications           # emails sent by the notification service
docker compose logs | grep <correlationId>        # one order across ALL services
```

To see the **compensation** path use `"paymentToken":"tok_fail"` – payment is declined, the order becomes `CANCELLED`
and `curl localhost:3002/stock` shows the stock restored. RabbitMQ UI: <http://localhost:15672> (user/pass in `.env.example`).

Stop and remove everything: `docker compose down -v`.

### Seed data

`PHONE-X` 50, `LAPTOP-15` 20, `KETTLE-1` 100, `LAMP-OAK` 2.

## Environment variables

All configuration is injected through the environment (12-factor III). Nothing is hard-coded in the images.

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `RABBITMQ_URL` | all services | `amqp://maltashop:maltashop_dev@rabbitmq:5672` | Broker connection string (built from the two variables below by Compose) |
| `RABBITMQ_USER` / `RABBITMQ_PASS` | Compose, rabbitmq | `maltashop` / `maltashop_dev` | Broker credentials (dev only – use a secret store in production) |
| `SERVICE_NAME` | all services | set per service | Appears in every log line |
| `PORT` | all services | 3001–3004 | HTTP port |
| `DB_PATH` | all services | `/data/<service>.db` | Location of that service's private SQLite file (mounted volume) |
| `TAG` / `IMAGE_PREFIX` | Compose | `dev` / `maltashop` | Image tag and registry prefix (CI sets these to the commit SHA / ghcr.io) |

## Tests

```bash
# per service (Node 22.13+)
cd services/order-service && npm ci && npm test
# contract test: does Order's order.placed still satisfy what Inventory needs?
node --test "contract-tests/*.test.js"
```

| Level | What | Where |
|---|---|---|
| Unit | request validation, stock reservation/compensation, provider rules, templates | `services/*/test` |
| Contract | consumer-driven: Inventory's `contracts/order-placed.consumer.json` vs Order's event builder | `contract-tests/` |
| Integration / end-to-end | real broker + all services, happy and failure paths | `scripts/smoke-test.sh` (CI job `integration`) |

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR: lint + unit tests (matrix per service) → contract tests → build each
image **once** (tagged with the commit SHA) → integration test using those exact images → push to GitHub Container Registry
(main branch only).

## Repository layout

```
services/<name>-service/   src/, test/, Dockerfile (multi-stage, non-root, HEALTHCHECK), package.json
contract-tests/            consumer-driven contract test
scripts/                   smoke-test.sh, replay-duplicate.mjs
k8s/                       sample Kubernetes manifests for the report (not required to run the prototype)
docs/LAB_GUIDE.md          step-by-step lab instructions and screenshot checklist
docker-compose.yml         whole system, one command
```

## Known limitations (deliberate, discussed in the report)

- No transactional outbox: an order is saved and then published; a crash between the two would lose the event.
- SQLite per service keeps the prototype dependency-free; production would use managed PostgreSQL per service.
- Code in `src/common` is copied into each service rather than shared as a library, to keep services independently deployable.
- Authentication, API gateway, rate limiting, tracing and metrics are described in the report but not implemented here.
- Payment provider is simulated; no real card data is ever handled.
