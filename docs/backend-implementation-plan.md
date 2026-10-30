# Backend Implementation Plan — FOX MLO v2

Target design: [`backend-architecture.md`](backend-architecture.md). UX source: [`UX_design_implementation.pdf`](UX_design_implementation.pdf).

## Progress

| Phase | Status | Notes |
|---|---|---|
| 0 — Foundations | **Done** (branch `feat/backend-v2-temporal`) | Alembic (baseline `0001` adopts the existing v1 tables), async SQLAlchemy next to the sync v1 session, `temporalio 1.35.0`. New packages: `domain/`, `realtime/`, `temporal/`, `workflows/`, `activities/`; routers stay in `app/routers/`. Still to do: `get_actor()`, moving v1 services into `integrations/` (Phase 3). |
| 1 — Infrastructure | **Done** | `temporal-setup` → `temporal` 1.32.1 → `temporal-namespace` (`fox-mlo`, 720 h); `temporal-ui` 2.57.0 on 127.0.0.1:8088; `worker`; `polylang-mock`; `backend` renamed to `api`. The setup job creates the Temporal databases itself, so `init.sql` is unchanged. |
| 2 — Data model + realtime | **Done** | Migration `0002`: v2 tables, seeded templates, `events` + `notify_event()` trigger. One LISTEN connection per api process → broadcaster → `GET /api/v1/events/stream` (SSE, scopes, `Last-Event-ID` replay, heartbeat, `resync`). Verified end to end: `POST /api/v1/system/check-workflow` → Temporal → worker activity → `events` → NOTIFY → SSE; a rolled-back insert is never delivered. |
| 3 — Integrations | Next | |
| 4 — Workflows | Planned | |
| 5 — API v2 | Planned | |
| 6 — Frontend | Planned | |
| 7 — Hardening | Planned | |

Tests: `cd services/backend && uv run python -m pytest` (15 tests: status mapping, broadcaster, Temporal workflow in the time-skipping test server).

Each phase ends in a working, testable system and can be merged on its own. Phases 1–3 can partly run in parallel.

---

## Phase 0 — Foundations

**Goal:** a clean base to build on, with no behavior change.

- [ ] Add **Alembic**; generate a baseline migration from the current models; remove `create_all` from startup.
- [ ] Switch DB access to **SQLAlchemy 2 async + psycopg 3 async** (`create_async_engine`). Keep the v1 routers working.
- [ ] Restructure `services/backend/app/`:
  ```
  app/
    api/            routers (v2), dependencies (get_session, get_actor, get_temporal)
    domain/         enums (TaskType, TaskStatus, WorkflowStatus), status mapping
    db/             models, session, migrations (alembic)
    realtime/       listener, broadcaster, sse
    workflows/      OrderWorkflow, PositionWorkflow, PlunetSyncWorkflow
    activities/     plunet, polylang, xliff, qa, deliver, projection
    integrations/   plunet_gateway.py, source_connector.py, polylang_connector.py
    worker.py       Temporal worker entrypoint
    main.py         FastAPI entrypoint
  ```
- [ ] Add dependencies: `temporalio`, `alembic`, `sse-starlette`, `pytest-asyncio`.
- [ ] `get_actor()` dependency that returns `"anonymous"` (placeholder for future auth).

**Done when:** `docker compose up` works as before and `alembic upgrade head` runs on an empty database.

---

## Phase 1 — Infrastructure: Temporal + worker + Polylang mock

**Goal:** all services run; a "hello" workflow completes end to end.

- [ ] **Temporal on the latest release** (server and admin-tools `1.32.1`, UI `2.57.0`, SDK `temporalio 1.35.0`). The old all-in-one `auto-setup` image stopped at 1.29, so the setup follows Temporal's current reference layout: one-shot jobs plus the plain server image.
  - `services/temporal/Dockerfile`: `FROM temporalio/server:1.32.1` + our `dynamicconfig/`.
  - `services/temporal/admin-tools.Dockerfile`: `FROM temporalio/admin-tools:1.32.1` + `scripts/setup-postgres.sh` and `scripts/create-namespace.sh`. Both scripts are idempotent, so they are safe on every start.
- [ ] **docker-compose additions:**
  ```yaml
  temporal-setup:      # creates/updates schemas in databases temporal + temporal_visibility, then exits
    build: { context: ./services/temporal, dockerfile: admin-tools.Dockerfile }
    command: ["/scripts/setup-postgres.sh"]
    depends_on: { postgres: { condition: service_healthy } }

  temporal:
    build: ./services/temporal
    environment: [DB=postgres12, POSTGRES_SEEDS=postgres, POSTGRES_USER, POSTGRES_PWD, BIND_ON_IP=0.0.0.0, DYNAMIC_CONFIG_FILE_PATH]
    depends_on: { temporal-setup: { condition: service_completed_successfully } }
    healthcheck: nc -z localhost 7233       # no host port (7233 stays internal)

  temporal-namespace:  # registers namespace fox-mlo (30-day retention), then exits
    build: { context: ./services/temporal, dockerfile: admin-tools.Dockerfile }
    command: ["/scripts/create-namespace.sh"]
    depends_on: { temporal: { condition: service_healthy } }

  temporal-ui:
    image: temporalio/ui:2.57.0
    ports: ["127.0.0.1:${TEMPORAL_UI_HOST_PORT:-8088}:8080"]

  worker:
    build: ./services/backend
    command: ["uv", "run", "python", "-m", "app.worker"]
    depends_on: { temporal-namespace: { condition: service_completed_successfully } }

  polylang-mock:
    build: ./services/polylang-mock
  ```
  Rename `backend` → `api` (update `scripts/deploy.sh`, `start_locally.sh`, and the frontend `VITE_BACKEND_URL`).
- [ ] **`services/polylang-mock/`** (FastAPI, ~200 lines):
  - `GET /wp-json/pll/v1/languages`
  - `GET /wp-json/wp/v2/posts?lang=` and `GET /wp-json/wp/v2/posts/{id}`, each post with `lang` and `translations`
  - `POST /wp-json/wp/v2/posts` and `POST /wp-json/wp/v2/posts/{id}?lang=&translations[xx]=`
  - **mock-only** `GET /wp-json/pll/v1/posts/{id}/xliff?target=` → serves files from `fixtures/polylang/`
  - In-memory store seeded from a JSON file; a reset endpoint for tests.
- [ ] Health endpoint checks Temporal and Polylang.
- [ ] Update `.github/workflows/deploy.yml` and `scripts/deploy.sh` for the new services.

**Done when:** a `HelloWorkflow` started from a test route appears as completed in Temporal UI, and `curl polylang-mock/wp-json/pll/v1/languages` returns data.

---

## Phase 2 — Data model v2 + realtime bus

**Goal:** the new tables exist, and any event written appears live in a browser.

- [ ] Alembic migration: `customers`, `resources`, `workflow_templates`, `orders`, `positions`, `tasks`, `events`; re-link `xliff_segments` to `positions`. Indexes: `events(position_id, id)`, `events(order_id, id)`, `tasks(position_id, seq)`, `orders(status)`, `orders(pm_resource_id)`.
- [ ] Seed `workflow_templates`: Standard, Light, Regulated (from the UX design).
- [ ] Migration with the **`notify_event()` trigger** on `events` (see architecture §4.1).
- [ ] `realtime/listener.py`: one async psycopg connection per api process, `LISTEN fox_events`, with automatic reconnect plus backoff. On reconnect, broadcast a `resync` marker so clients refetch.
- [ ] `realtime/broadcaster.py`: subscriber registry keyed by scope (`all`, `order:{id}`, `position:{id}`), and a bounded queue per client (slow clients get dropped, then reconnect).
- [ ] `GET /api/v1/events/stream`: SSE with `id:` = event id, replay from `Last-Event-ID`, 15 s heartbeat.
- [ ] `events.py` repository: `insert_event(session, …)` used by everyone.

**Tests:** inserting an event from a separate connection reaches an SSE test client within 1 s. A client that disconnects and reconnects with `Last-Event-ID` receives the missed events. A rolled-back transaction produces no notification.

**Done when:** `psql -c "INSERT INTO events …"` shows up live in `curl -N /api/v1/events/stream`.

---

## Phase 3 — Integrations

**Goal:** tested gateways for Plunet and Polylang, used only by activities.

- [ ] `PlunetGateway` (refactor `plunet_client.py` and `plunet_service.py`):
  - session reuse and re-login, typed results, `PlunetError` with business and technical subclasses
  - `create_order`, `create_quote`, `convert_quote_to_order`, `get_quote_status`
  - `create_item(order, position)`, `upload_document(item, xliff)`
  - `create_job(item, task_type)`, `get_job_status(job_id)`, `set_job_status(job_id, CANCELED)`
  - `list_resources()` (PMs), `list_customers()`
  - check every SOAP call against the Plunet API doc (`DataOrder30`, `DataItem30`, `DataJob30`, `DataQuote30`)
- [ ] `PlunetStatusMapper`: `JobStatus` → `TaskStatus` (architecture §6.1). The raw Plunet status is stored; the UI state is derived from it, so both systems always show the same thing.
- [ ] Write-back calls for two-way sync: `set_job_status`, `assign_resource`, `set_item_status`, `get_job_prices` (cost comes from Plunet job prices).
- [ ] `SourceConnector` protocol + `PolylangConnector` (httpx, base URL and auth from env).
- [ ] QA rules as decided (architecture §5.3): blocking = empty target, placeholder mismatch, inline-tag mismatch, malformed XML; warnings = target equals source, number mismatch, length, whitespace.
- [ ] Move the XLIFF parsing and QA checks from `xliff_processor.py` into pure functions (`parse`, `check_placeholders`, `check_lengths`) that return structured findings.
- [ ] Recorded fixtures (VCR-style or a fake gateway) so tests do not hit the live Plunet portal.

**Done when:** unit tests cover the gateway with fakes, and one manual smoke script creates and cancels a test order on the real Plunet.

---

## Phase 4 — Temporal workflows and activities

**Goal:** an order runs from creation to delivery and can be controlled.

- [ ] Activities (`activities/`), all idempotent:
  - `projection.record_task_state`, `projection.record_event`, `projection.set_order_status`
  - `plunet.create_order|create_quote|convert_quote|create_item|create_job|cancel_jobs|upload_document` (queue `fox-plunet`)
  - `polylang.fetch_xliff`, `polylang.publish_translation`
  - `xliff.parse_and_store`, `qa.run_checks`, `deliver.to_endpoint`
- [ ] Retry policies: technical errors use 5 attempts, exponential backoff up to 5 min. `BusinessError` is listed in `non_retryable_error_types`.
- [ ] `PositionWorkflow` (architecture §5.2–5.4):
  - task loop with cursor; per-task handlers (automatic vs human Plunet task)
  - updates with validators: `pause`, `resume`, `retry`, `restart_from`, `cancel`
  - signal `plunet_job_status(job_id, status)`; overdue timer, which emits a WARN event
  - query `state` (for debugging and for the api if the projection lags)
  - cancellation: cancel running activity handles, run `cancel_jobs` in a non-cancellable scope, then record `CANCELLED`
- [ ] `OrderWorkflow`: create in Plunet → if quote, `wait_condition(accepted or rejected)` → start child `PositionWorkflow`s (`parent_close_policy=REQUEST_CANCEL`) → compute order status as children report.
- [ ] `POST /api/v1/plunet/callbacks`: verifies the shared secret, maps the Plunet event to `(order | job) + status`, and signals the workflow. Register the callbacks in Plunet at worker start (idempotent).
- [ ] `PlunetSyncWorkflow` as a **Temporal Schedule** (every 2 min, overlap policy `SKIP`): reconciliation. Reads open jobs and quotes from the DB, asks Plunet for status and prices, signals workflows on change, and logs a `WARN` event when it corrects a missed callback.
- [ ] Every FOX MLO action that changes a job (cancel, restart, assign) calls Plunet **first** and updates the local state only after Plunet confirms.
- [ ] `worker.py`: registers workflows and activities on both task queues; graceful shutdown.

**Tests:** use the Temporal **time-skipping test environment** (`WorkflowEnvironment.start_time_skipping()`) with mocked activities:
- happy path through all 6 tasks
- QA fails → retry → completes
- pause during TRA → no new task starts → resume
- restart from REV resets later tasks
- cancel with reason → `cancel_jobs` called → status `CANCELLED`
- quote waits; `quote_accepted` sent twice → positions start only once
- invalid update (resume while running) → rejected
- replay test against saved histories (protects determinism on future changes)

**Done when:** in Docker, creating an order with 2 positions runs to `COMPLETED` with mocked human tasks (a dev endpoint to force the Plunet job status), and every step is visible in Temporal UI and in the `events` table.

---

## Phase 5 — API v2

**Goal:** every endpoint the new UI needs (architecture §8).

- [ ] Routers: `orders`, `positions`, `events`, `reference` (Plunet resources and customers, Polylang, templates), `analytics`, `health`.
- [ ] `POST /orders`: validate, insert order and positions in one transaction plus a `CREATED` event, then start `OrderWorkflow` with `id=order-{id}` (start is idempotent on workflow id, so a retried request is safe).
- [ ] Actions call Temporal **updates**; validator rejections map to `409`; an unknown workflow maps to `404`.
- [ ] List filters (`attention` = failed, paused or overdue), pagination, sorting.
- [ ] Analytics queries on `tasks`: duration per task type, cost, error counts, grouped by PM, customer or order, over a time range.
- [ ] Pydantic v2 schemas generated into an OpenAPI spec; the frontend generates its TypeScript client from it.
- [ ] Keep the v1 `/etl/*` routes until the frontend has switched, then delete them (Phase 7).

**Tests:** API tests with a test database and a Temporal test server (or a mocked Temporal client for fast unit tests).

---

## Phase 6 — Frontend integration (outline; detailed in the UX plan)

- [ ] React Router pages from the design: Orders, New order, Order detail, Position/Workflow detail, Analytics.
- [ ] `useEventStream(scope)` hook (EventSource + refetch on `resync`) wired into the pages, e.g. with TanStack Query invalidation.
- [ ] i18n EN/FR.

---

## Phase 7 — Hardening and cleanup

- [ ] Remove the v1 `etl_jobs` flow, the `simulate-destination` route and the old tables (migration).
- [ ] `events` retention job (Temporal Schedule, daily): delete or archive rows older than 180 days.
- [ ] Backups: `pg_dump` of `fox_mlo`, `temporal` and `temporal_visibility`; a restore test.
- [ ] Observability: Temporal SDK metrics (Prometheus endpoint on the worker), api request logs, alerts on failed workflows and listener reconnect loops.
- [ ] Load check: 50 orders × 10 positions; SSE with 20 open clients.
- [ ] Update `docs/architecture.md`, `api-endpoints.md` and `directory-structure.md`.

---

## Testing strategy (summary)

| Level | Tooling | Covers |
|---|---|---|
| Unit | pytest | XLIFF parse and QA, status mapping, gateways with fakes |
| Workflow | `temporalio.testing` (time-skipping) | All control paths, quote acceptance, determinism replay |
| Integration | docker compose + pytest | API ↔ Temporal ↔ Postgres ↔ polylang-mock; SSE delivery |
| Manual | Plunet test portal | One real order, quote → order, cancel |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Plunet SOAP is slow or rate-limited | Dedicated `fox-plunet` queue with low concurrency; retries with backoff; polling every 2 min, not per workflow. |
| Workflow code changes break running workflows | `workflow.patched()` versioning + replay tests in CI. |
| Missed NOTIFY (listener down) | Outbox table + `Last-Event-ID` replay + `resync` refetch. |
| DB read model and Temporal state drift apart | All writes through `record_task_state`; a workflow `state` query for checks; an admin "re-project" activity. |
| Temporal upgrades | Pinned image versions; upgrade one minor version at a time; `temporal-setup` applies schema updates before the server starts. |
| Plunet callbacks cannot reach the VPS | Polling reconciliation already covers every state change, just with up to 2 min delay. |
| Temporal shares the Postgres server | Separate databases; monitor connections; split to its own server later if needed. |

## Decisions (2026-10-30)

| # | Question | Decision |
|---|---|---|
| 1 | Can Plunet reach the VPS for callbacks? | Probably. Callbacks are the main path; polling every 2 min stays as reconciliation. Check reachability in Phase 4. |
| 2 | Who owns job data and states? | Plunet and FOX MLO stay in sync with the same states. Plunet is the source of truth; FOX MLO writes changes to Plunet first and mirrors Plunet changes (callbacks + polling). |
| 3 | QA rules | Default set in architecture §5.3 (blocking vs warning). |
| 4 | Cost source | Plunet job prices. |
| 5 | Hosting | The single VPS, including Temporal, for now. |
| – | Temporal version | Latest stable: server 1.32.1, UI 2.57.0, Python SDK 1.35.0. |

## Still open

1. Which Plunet events can be registered as callbacks on the FOX Plunet instance (license and version 10.26.2)?
2. Required fields when creating PM, TRA and REV jobs (due date, price list, resource) for the FOX Plunet setup.
