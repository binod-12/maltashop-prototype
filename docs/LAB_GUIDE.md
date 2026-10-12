# Lab Guide – Unit 5 MaltaShop Prototype

Everything the brief's Section 6 and "Evidence" boxes ask for, in the order you should do it.
Deadline: **22 Oct 2026**. Allow about 1–2 hours for the lab itself, plus time for the report.

---

## 0. What was verified and what was not

- ✅ All 17 automated tests pass (14 unit, 3 contract).
- ✅ All four services were run against a **real RabbitMQ 3.12 broker** and `scripts/smoke-test.sh` passed: happy path,
  payment-declined compensation (stock restored), out-of-stock cancellation, idempotent POST retry, notifications.
- ✅ A duplicate message redelivery changed nothing (stock, payments and emails were not doubled).
- ⚠️ **Not tested:** `docker compose up --build`, the Dockerfiles and the GitHub Actions workflow. The workspace this was
  built in has no Docker daemon and cannot reach GitHub. They follow standard patterns, but **you run them first** (Step 1)
  and fix anything that breaks before taking screenshots. Troubleshooting is at the bottom.

---

## 1. Run the system (10 min)

Install **Docker Desktop** (Windows/Mac) and **Git**. On Windows, run the `bash` commands in **Git Bash** (installed with
Git) or WSL; the `docker` and `curl` commands also work in PowerShell (use `curl.exe`).

```bash
cd maltashop-prototype
docker compose up --build        # first build takes a few minutes
```

In a second terminal: `docker compose ps` → every service should show **healthy**. Then:

```bash
bash scripts/smoke-test.sh
```

Expected last line: `ALL SMOKE TESTS PASSED`.

---

## 2. Create the Git repository with real history (do this over several days)

The brief requires that **the commit history shows the prototype developing over time, not a single upload**. Do not copy
the whole folder in at once. Commit in stages, ideally on different days, and write the commit messages yourself.

```bash
git init -b main
git add .gitignore README.md          && git commit -m "Add README skeleton and gitignore"
git add services/order-service        && git commit -m "Order service: POST /orders, SQLite store, order.placed event"
git add docker-compose.yml .env.example && git commit -m "Add RabbitMQ and order-service to compose"
git add services/inventory-service    && git commit -m "Inventory service: stock reservation and consumer contract"
git add services/payment-service      && git commit -m "Payment service with simulated provider"
git add services/notification-service && git commit -m "Notification service as pure subscriber"
git add contract-tests                && git commit -m "Add Order->Inventory contract test"
git add scripts                       && git commit -m "Add smoke test and duplicate-replay scripts"
git add .github                       && git commit -m "Add CI/CD workflow"
git add k8s docs                      && git commit -m "Add Kubernetes samples and lab guide"
```

Better still: make small real changes between commits (rename a field, add a log line, fix a typo you find while testing).
Authentic history also protects you in the demonstration, where you may be asked to explain how the work evolved.

Then create an empty repo on GitHub, push, and **share it with your lecturer** (Settings → Collaborators, or make it public):

```bash
git remote add origin https://github.com/<your-username>/maltashop-prototype.git
git push -u origin main
```

Put the URL in the report appendix.

---

## 3. Pipeline evidence (Section 3 of the report)

1. After the first push, open the repo → **Actions** tab. The `ci-cd` workflow runs automatically.
2. Wait for green ticks on `test`, `contract`, `build`, `integration`, `publish`.
3. **Screenshot** the run page showing all jobs passed (this is the "screenshot of one passing pipeline run").
4. Copy `.github/workflows/ci.yml` into the report as the "pipeline workflow file".

If `publish` fails with a permissions error: repo Settings → Actions → General → Workflow permissions → *Read and write*.
You may explain in the report that `publish` only runs on `main`. If it is a problem, a green run of the first four jobs is
still valid evidence.

---

## 4. Screenshot checklist (Section 6.3 and diagrams)

Take these while the system is running. Crop to the relevant part and make the text readable.

| # | Screenshot | How | Report |
|---|---|---|---|
| 1 | `docker compose ps` showing all services **healthy** | terminal | 6.2 / 6.3 |
| 2 | Order request **and** response (`202`, orderId, correlationId) | the `curl -i -X POST …` command from the README | 6.3 |
| 3 | The order later shows `CONFIRMED` | `curl localhost:3001/orders/<id>` | 6.3 |
| 4 | Event **consumed by the second service** | `docker compose logs inventory-service` showing `received order.placed` / `inventory.reserved` | 6.3 |
| 5 | **Same correlation ID in both services' logs** | `docker compose logs \| grep <correlationId>` (all four services appear) | 6.3 |
| 6 | Compensation: order with `tok_fail` → `CANCELLED`, stock restored | `curl localhost:3002/stock` before and after | 6.1 |
| 7 | Duplicate delivery ignored | `python scripts/replay_duplicate.py <orderId> <messageId> <correlationId>` then the `duplicate … ignored` log lines (messageId is in the `event.published` log line for `order.placed`) | 6.1 |
| 8 | RabbitMQ management UI, exchange and queues (http://localhost:15672) | browser | 6.3 |
| 9 | Passing pipeline run | GitHub Actions page | 3 |
| 10 | Test output (`python -m pytest`, contract test) | terminal | 3.2 |

Useful commands for #5 on Windows PowerShell: `docker compose logs | Select-String <correlationId>`.

---

## 5. Where each report answer is supported in the code

| Brief item | Evidence in this repo |
|---|---|
| 2.1 container diagram, AI Recommendation placement | Draw it yourself (must be your own work). Recommendation would be a separate **subscriber** on the same exchange (`order.placed`, `order.confirmed`, browsing events): publish/subscribe means it never calls or blocks checkout. |
| 2.2 patterns | Database per service (each `DB_PATH`), publish-subscribe (`app/common/mq.py`), saga (below), API gateway/circuit breaker/strangler fig (discuss; not implemented) |
| 2.3 12-factor | III config in env (compose, README table), XI logs as stdout events (`app/common/log.py`), VI stateless processes (state only in `/data` volume), IX disposability (`os._exit(1)` on broker loss, `restart: unless-stopped`), X dev/prod parity (same image everywhere) |
| 3.1 CI/CD, build once | `.github/workflows/ci.yml`: image built once, tagged with SHA, the *same* image is integration-tested and pushed |
| 3.2 test pyramid, contract test | `services/*/test`, `contract-tests/`, `scripts/smoke-test.sh`; contract between **Order** and **Inventory** |
| 3.3 canary / rollback | `k8s/payment-canary.yaml` |
| 4.1 Kubernetes | `k8s/order-service.yaml` (Deployment, probes, requests/limits, HPA). Services using `/health` and `/ready` map directly to liveness/readiness probes |
| 4.2 logging | JSON schema in `app/common/log.py`: `timestamp, level, service, correlationId, event, message` |
| 5.3 ADRs | Message broker (RabbitMQ vs Kafka vs cloud queue) and observability stack: you write these; rationale for RabbitMQ in this repo is durable queues, DLQ, simple ops for a team new to distributed systems |
| 6.1 saga, compensation, idempotency | See below |
| 6.2 Dockerfile and Compose | `services/*/Dockerfile`, `docker-compose.yml` |

### 6.1 – the code to quote (annotated snippets)

- **Choreography saga**: Order publishes `order.placed` (`services/order-service/app/main.py`), Inventory reacts and publishes
  `inventory.reserved`, Payment reacts and publishes `payment.completed` or `payment.failed`, Order confirms or cancels.
  No service calls another directly and no distributed transaction exists.
- **Compensating action**: `release()` in `services/inventory-service/app/stock.py`, triggered by `payment.failed`.
- **Idempotency**: `mark_processed()` in `app/common/db.py`. It inserts `(messageId, handler)` in the *same transaction* as the
  business change, so a redelivery is detected and skipped. The POST endpoint also honours an `Idempotency-Key` header.
- **Broker features that support it**: durable queues and persistent messages (survive restart), publisher confirms,
  manual acks (a message is only removed after the handler succeeds), a dead-letter exchange for poison messages
  (`app/common/mq.py`).
- **Honest limitation to state in 6.3**: saving the order and publishing the event are two steps (no transactional outbox),
  RabbitMQ gives at-least-once delivery so idempotency is mandatory, and payment has no timeout/circuit breaker.

---

## 6. Demonstration / viva preparation

The brief says you may be asked to demonstrate and explain. Be able to answer:

1. *Why choreography, not orchestration?* Four services and a linear flow; no central coordinator to run or fail. Trade-off: the flow is spread across services, harder to see. At larger scale an orchestrator becomes attractive.
2. *What happens if the notification service is down?* Messages wait in its durable queue; checkout is unaffected (the March incident).
3. *What if Payment crashes after charging but before publishing?* Redelivery repeats the handler; the unique `order_id` in `payments` and the processed-events table stop a double charge. Strictly, the provider call itself needs an idempotency key too (limitation).
4. *Where is the correlation ID created?* At the edge (Order's POST or an API gateway header), carried in AMQP `correlationId`, logged by every service.
5. *Why a separate `/health` and `/ready`?* Liveness restarts a stuck process; readiness removes a pod from traffic when the broker is unreachable, without restarting it.
6. *Why is the code in `app/common` duplicated?* A shared library would couple release cycles of all services; duplication of 100 lines is the cheaper trade-off at this size.
7. *Why SQLite?* Keeps the prototype dependency-free while proving database-per-service; production: managed PostgreSQL per service.

Run through `docker compose logs` once so you recognise every line.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Service restarts with `could not connect to RabbitMQ` | Broker still starting; Compose waits for its health check, but give it 30 s. Check `docker compose logs rabbitmq`. |
| `pip install` fails during build | Check the pinned versions in `requirements.txt`; rebuild with `docker compose build --no-cache`. |
| Port already in use | Change the left side of the port mapping in `docker-compose.yml`, e.g. `"3101:3001"`. |
| `bash: scripts/smoke-test.sh` not found on Windows | Use Git Bash, or run from WSL. |
| Smoke test hangs on "did not reach CONFIRMED" | `docker compose logs --tail 50` and look for `event.handler_failed` or `contract violation`. |
| Want a clean slate | `docker compose down -v` (also deletes the data volumes). |
