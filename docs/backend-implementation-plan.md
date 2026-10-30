# Backend Implementation Plan — FOX MLO v2

Target design: [`backend-architecture.md`](backend-architecture.md). UX source: [`UX_design_implementation.pdf`](UX_design_implementation.pdf).

## Progress

| Phase | Status | Notes |
|---|---|---|
| 0 — Foundations | **Done** (branch `feat/backend-v2-temporal`) | Alembic (baseline `0001` adopts the existing v1 tables), async SQLAlchemy next to the sync v1 session, `temporalio 1.35.0`. New packages: `domain/`, `realtime/`, `temporal/`, `workflows/`, `activities/`; routers stay in `app/routers/`. Still to do: `get_actor()`, moving v1 services into `integrations/` (Phase 3). |
| 1 — Infrastructure | **Done** | `temporal-setup` → `temporal` 1.32.1 → `temporal-namespace` (`fox-mlo`, 720 h); `temporal-ui` 2.57.0 on 127.0.0.1:8088; `worker`; `polylang-mock`; `backend` renamed to `api`. The setup job creates the Temporal databases itself, so `init.sql` is unchanged. |
| 2 — Data model + realtime | **Done** | Migration `0002`: v2 tables, seeded templates, `events` + `notify_event()` trigger. One LISTEN connection per api process → broadcaster → `GET /api/v1/events/stream` (SSE, scopes, `Last-Event-ID` replay, heartbeat, `resync`). Verified end to end: `POST /api/v1/system/check-workflow` → Temporal → worker activity → `events` → NOTIFY → SSE; a rolled-back insert is never delivered. |
| 3 — Integrations | **Done** (branch `feat/backend-phase3-integrations`); smoke test passed on the live portal | Plunet SOAP gateway + in-memory fake, Polylang connector, XLIFF parser and QA rules, WSDL-validated tests. See Phase 3 below. |
| 4 — Workflows | **Done** (branch `feat/backend-phase4-workflows`); end to end in Docker with the fake Plunet | `OrderWorkflow`, `PositionWorkflow`, `PlunetSyncWorkflow` (Schedule), activities on two task queues, dev endpoints. See Phase 4 below. |
| 5 — API v2 | Planned | |
| 6 — Frontend | In progress | New UI built against a mock API (`VITE_API_MODE`, default `mock`); contract in `services/frontend/src/api/types.ts`. Wiring to real endpoints follows phases 3–5. v1 dashboard moved to `/legacy`. |
| 7 — Hardening | Planned | |

Tests: `cd services/backend && uv run python -m pytest` (116 tests: status mapping, broadcaster, Plunet gateway against the recorded WSDLs, Polylang connector, XLIFF and QA, workflows in the time-skipping test server, replay of saved histories).

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

- [x] `PlunetGateway` protocol + `SoapPlunetGateway` (`app/integrations/plunet/`):
  - one shared session, re-login once when Plunet reports an expired UUID; typed pydantic results
  - errors: `PlunetTechnicalError` (retried) and `PlunetBusinessError` / `PlunetAuthError` (not retried), on top of the shared `TechnicalError` / `BusinessError` in `app/integrations/errors.py`
  - `create_order`, `create_quote`, `get_quote_status`, `set_quote_status`, `get_order_id_for_quote`, `delete_order`, `delete_quote`
  - `create_item` (+ language combination), `set_item_status`, `upload_document` (item source folder)
  - `create_job`, `get_job`, `list_item_jobs`, `set_job_status`, `assign_resource`, `get_job_cost`
  - `list_customers` (active), `list_project_managers` (active internal resources), `version`
  - every SOAP call checked against the portal's own WSDLs, recorded in `tests/fixtures/plunet_wsdl/`
- [x] Status mapping `JobStatus` → `TaskStatus` (`app/domain/plunet_status.py`, done in phase 0); the gateway returns the raw Plunet status name.
- [x] Write-back calls for two-way sync: `set_job_status`, `assign_resource`, `set_item_status`, `get_job_cost` (sum of the job price lines in project currency).
- [x] `SourceConnector` protocol (`app/integrations/source.py`) + `PolylangConnector` (httpx, async; `publish_translation` creates or updates the linked post, so it is idempotent).
- [x] QA rules (architecture §5.3) in `app/xliff/qa.py`; parsing in `app/xliff/parse.py` (XLIFF 1.2 and 2.0, inline-tag signatures, markup without namespaces). Findings match the frontend `QaFinding` type.
- [x] `FakePlunetGateway` (in-memory) for tests and for running without a portal (`PLUNET_MODE=fake`).
- [x] Tests: SOAP calls replayed against the recorded WSDLs (unknown operation, argument or field and missing required fields fail), session expiry, error mapping, Polylang connector against the mock app in-process, QA rules. 79 tests.
- [x] `scripts/plunet_smoke.py --quote` passed on portal.foxtranslations.com (Plunet 10.26.2, 2026-10-30): order, item, document, TRA job, cost, cancel; quote, quote item, release, order lookup; everything deleted afterwards.

The v1 `xliff_processor.py` stays as is for the legacy `/etl` routes and is removed with them in Phase 7.

**Findings from the WSDLs:**
- The SOAP API has **no call that converts a quote into an order**. Conversion happens in Plunet (decision 6). FOX MLO sets the quote status to `ACCEPTED` and detects the new order through the quote's `orderID` list (`getQuoteObject`), polled by Phase 4. `getOrderIDFirstItem` is not usable: it fails (-100) on unconverted quotes.
- Items have no language fields on creation; the gateway adds the language pair with `DataItem30.addLanguageCombination` right after `insert2`.
- Plunet expects its own **language names** ("English", "French"), not codes. The gateway reads the active languages (`DataAdmin30.getAvailableLanguages`) and resolves a Polylang code or locale: exact locale first (`fr_CA` → "French (Canada)"), else the generic language (`de-at` → "German"; there is no German (Austria) on the FOX instance). An unknown language fails before anything is written.
- A quote accepts a PM and new items only while it is `NEW` / `IN_PREPARATION`. `create_quote` leaves it `IN_PREPARATION`; Phase 4 adds items and documents, then releases it with `PENDING`. If setting the PM fails, the quote is deleted.
- Job types on the FOX instance are `PRM` (project management), `TRA` and `REV`; there is no `PM`. Jobs are created with `insert3` (start and due date). Job prices come in the project currency (CAD for the test customer).
- `OrderIN` requires `rate`, `customerContactID` and `orderID`; `ItemIN` requires `status`, `taxType` and `totalPrice`. The gateway sends neutral defaults.

**Done when:** unit tests cover the gateway with fakes, and one manual smoke script creates and cancels a test order on the real Plunet.

---

## Phase 4 — Temporal workflows and activities

**Goal:** an order runs from creation to delivery and can be controlled.

- [x] Activities (`app/activities/`), all idempotent (each creation checks the id stored in the DB first and saves the new Plunet id in the same activity):
  - `projection.py` (queue `fox-orchestration`): `load_order`, `load_position`, `record_task` (task + position + recomputed order status + event in one transaction), `reset_tasks`, `close_position`, `update_order`, `set_position_workflow`, `collect_sync_targets`
  - `content.py`: `import_xliff` (Polylang → parse → segments), `run_qa`, `deliver` (Polylang / endpoint / none)
  - `plunet.py` (queue `fox-plunet`, sync zeep calls on a thread pool, `PLUNET_MAX_CONCURRENT_CALLS`): `plunet_create_project`, `plunet_set_quote_status`, `plunet_adopt_order`, `plunet_create_item`, `plunet_upload_source`, `plunet_set_item_status`, `plunet_create_job`, `plunet_job_outcome`, `plunet_cancel_job`, `plunet_cancel_position`, `plunet_fetch_translation`, `plunet_poll`; `dev_*` helpers for the fake Plunet
- [x] Retry policy `RETRY`: 5 attempts, backoff ×2 up to 5 min. `BusinessError` becomes a non-retryable `ApplicationError(type="BusinessError")` (`activities/common.py`).
- [x] `PositionWorkflow`: task loop with cursor; IMPORT / Plunet job (PM, TRA, REV) / QA / DELIVER handlers. A failed task waits for a person (`retry`, `restart_from` or `cancel`).
  - updates with validators: `pause`, `resume`, `retry` (only on a failed task), `restart_from(seq ≤ cursor)`, `cancel` (reason required)
  - signal `plunet_job_status`; overdue timer up to the order deadline emits one WARN event
  - query `state`
  - cancel: Plunet first (open jobs and the item → `CANCELED`), then `CANCELLED` locally. If the Plunet cleanup fails, the cancellation still stands and a WARN event asks for a manual check.
  - retry and restart of a Plunet task create a **new** job; restart cancels the open job in Plunet first.
- [x] `OrderWorkflow`: create in Plunet. Quote: create items, upload the .xliff, release to `PENDING`, wait. Accepted in FOX MLO → `ACCEPTED` in Plunet, then wait for the PM's conversion; converted → `plunet_adopt_order` matches the order items to positions by the `FOX-P{id}` tag. Then child `PositionWorkflow`s `position-{id}` (`REQUEST_CANCEL`). Signals are idempotent.
- [x] `PlunetSyncWorkflow` as the Schedule `plunet-sync` (every `PLUNET_SYNC_SECONDS`, overlap `SKIP`): reads open jobs and quotes awaiting acceptance, asks Plunet, signals the workflows that changed. Missing workflows are skipped.
- [x] Job creation defaults (decision 7): due date = order deadline, start date = now, no resource, prices from Plunet's price list.
- [x] `worker.py`: two workers (`fox-orchestration`, `fox-plunet`), creates or updates the sync schedule, graceful shutdown on SIGINT/SIGTERM.
- [x] Dev endpoints (`DEV_ENDPOINTS=true`, `app/routers/dev.py`): `POST /dev/orders`, `/dev/orders/{id}/accept|reject`, `/dev/positions/{id}/{pause|resume|retry|cancel|restart}`, `GET /dev/positions/{id}/state`; with `PLUNET_MODE=fake` also `/dev/plunet/jobs/{job_id}/status`, `/dev/plunet/quotes/{order_id}/convert`, `/dev/plunet/sync`.

**Tests** (`tests/test_workflows.py`, fakes in `tests/workflow_fakes.py`, time-skipping server): happy path through 6 tasks; QA fail → retry; pause during TRA → resume; restart from REV; restart while a job is open cancels it in Plunet; cancel with reason and the reason-required rejection; cancel when the Plunet cleanup fails; invalid updates rejected; job cancelled in Plunet → FAILED → retry with a new job; overdue WARN once; quote accepted twice → `ACCEPTED` once, converted → positions start; quote rejected in Plunet; direct order; sync signals and missing workflows. The happy-path history is replayed in the test and saved in `tests/fixtures/histories/`; `FOX_WRITE_HISTORIES=1` refreshes it after an intended change.

**Verified in Docker (2026-10-30)** with `PLUNET_MODE=fake DEV_ENDPOINTS=true PLUNET_SYNC_SECONDS=15`: an order with 2 positions (standard template, fr and de-at) ran to `COMPLETED`, each job change travelling fake Plunet → sync → signal (≈2 s with the schedule triggered); a quote went through accept → convert → `COMPLETED`. Every step is in the `events` table and in Temporal UI.

**Findings:**
- The fake Plunet lives in the worker's memory: restarting the worker forgets its objects while the database keeps their ids. Start new dev orders after a restart.
- The translated file is read from the last delivered job's OUT folder (`ORDER_JOB_OUT`); QA runs on that file.

**Done when:** in Docker, creating an order with 2 positions runs to `COMPLETED` with mocked human tasks (a dev endpoint to force the Plunet job status), and every step is visible in Temporal UI and in the `events` table. ✔

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
| Changes made in Plunet show up late | Polling every 2 min is the only sync path; changes appear within about 2 min. The interval can be lowered if the SOAP load allows. |
| Temporal shares the Postgres server | Separate databases; monitor connections; split to its own server later if needed. |

## Decisions (2026-10-30)

| # | Question | Decision |
|---|---|---|
| 1 | Plunet callbacks? | **Not used.** The 2-minute polling (`PlunetSyncWorkflow`) carries the sync alone. |
| 2 | Who owns job data and states? | Plunet and FOX MLO stay in sync with the same states. Plunet is the source of truth; FOX MLO writes changes to Plunet first and mirrors Plunet changes (polling every 2 min). |
| 3 | QA rules | Default set in architecture §5.3 (blocking vs warning). |
| 4 | Cost source | Plunet job prices. |
| 5 | Hosting | The single VPS, including Temporal, for now. |
| 6 | Quote acceptance in FOX MLO (the API cannot convert a quote) | FOX MLO sets the quote to `ACCEPTED`; the PM converts it in Plunet; FOX MLO detects the new order and starts the workflows. |
| 7 | Required job fields | Common defaults until known: due date from the position (else order) deadline, start date now, no resource on creation, prices from Plunet's price list. Adjust once the FOX Plunet setup is confirmed. |
| – | Temporal version | Latest stable: server 1.32.1, UI 2.57.0, Python SDK 1.35.0. |

## Still open

1. Confirm the required job fields on the FOX Plunet setup (decision 7 uses common defaults).
2. Job type short names `PM` and `REV` on the FOX instance (`TRA` is confirmed); check with `scripts/plunet_smoke.py --job-type PM` / `REV`.
