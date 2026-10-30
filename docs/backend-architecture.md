# Backend Architecture — FOX MLO v2

This document describes the target backend for the redesigned FOX MLO: an orchestrator for **Order → Position → Workflow → Tasks** (Plunet Auftrag → Item → workflow → Plunet Jobs).
It builds on the UX decisions in [`UX_design_implementation.pdf`](UX_design_implementation.pdf). Implementation status and findings: [`backend-implementation-plan.md`](backend-implementation-plan.md). For users: [`user-guide.md`](user-guide.md).

Three choices define it:

1. **FastAPI** is the API: it serves commands, queries and live updates to the frontend.
2. **Temporal** (new service) runs the workflows durably: state, retries, pause/resume, cancel, restart, waiting on people.
3. **PostgreSQL** is the database **and** the realtime message bus: an `events` table plus `LISTEN/NOTIFY`, pushed to browsers over Server-Sent Events.

---

## 1. System overview

```
                         ┌──────────────────────────────┐
  Browser (React)  ◄─SSE─┤  api  (FastAPI)              │
        │                │  - REST commands & queries   │
        └──── REST ─────►│  - SSE /events/stream        │
                         │  - 1 LISTEN connection       │
                         └──┬─────────────┬─────────────┘
                start/signal│             │ SQL (read model)
                /update/query│             │ LISTEN fox_events
                         ┌──▼───────┐  ┌──▼──────────────────────────┐
                         │ temporal │  │ postgres 16                 │
                         │ server   ├──►  db fox_mlo   (app data)    │
                         │ :7233    │  │  db temporal (Temporal)     │
                         └──▲───────┘  │  db temporal_visibility     │
               poll task    │          └──▲──────────────────────────┘
               queues       │             │ SQL writes + NOTIFY (via trigger)
                         ┌──┴─────────────┴────────────┐
                         │  worker (Temporal Python SDK)│
                         │  - workflows (deterministic) │
                         │  - activities (all I/O)      │
                         └──┬──────────────┬───────────┘
                            │ SOAP          │ REST
                   ┌────────▼───────┐ ┌─────▼──────────────┐
                   │ Plunet BM      │ │ Polylang (mock now, │
                   │ (SOAP 1.2)     │ │ WordPress later)    │
                   └────────────────┘ └────────────────────┘

   temporal-ui 127.0.0.1:8088  (operators only; never exposed publicly)
```

### Services (docker-compose)

| Service | Image / build | Role | Ports |
|---|---|---|---|
| `postgres` | `services/db` (PostgreSQL 16) | App data, events bus, Temporal persistence (separate databases) | 5433→5432 |
| `temporal-setup` | `services/temporal/admin-tools.Dockerfile` (`temporalio/admin-tools:1.32.1`) | One-shot job: creates or upgrades the Temporal schemas, then exits | – |
| `temporal` | `services/temporal/Dockerfile` (`temporalio/server:1.32.1`) | Workflow engine | 7233 (internal only) |
| `temporal-namespace` | same image as `temporal-setup` | One-shot job: registers the `fox-mlo` namespace | – |
| `temporal-ui` | `temporalio/ui:2.57.0` | Debug and operations UI | 127.0.0.1:8088 only |
| `api` | `services/backend` | FastAPI: REST + SSE | 8000 |
| `worker` | `services/backend` (same image, different command) | Runs Temporal workflows and activities | – |
| `polylang-mock` | `services/polylang-mock` (new) | Mock Polylang/WordPress REST API + ready-made `.xliff` | 8090 (internal) |
| `frontend` | `services/frontend` | React app | 3000 |

`api` and `worker` share one codebase (`services/backend/app`) and one Docker image. They differ only in their start command. This keeps models, schemas and clients in one place.

---

## 2. Responsibilities: who owns what

| Concern | Owner | Why |
|---|---|---|
| **Execution state** (which Task runs, retries, timers, waiting) | **Temporal** | Durable, replayable; survives restarts of api/worker. |
| **Business data and read model** (orders, positions, task states for the UI, analytics) | **Postgres `fox_mlo`** | Fast queries, joins, analytics; the UI never queries Temporal for lists. |
| **Realtime notifications** | **Postgres `events` + NOTIFY** | One bus, transactional with the data it describes. |
| **Commands** (start, pause, cancel…) | **api → Temporal** | api validates, then signals or updates the workflow. Never via NOTIFY. |
| **External I/O** (Plunet, Polylang, destinations) | **worker activities** | Retries, timeouts and heartbeats managed by Temporal. |

Rule: **Temporal decides, Postgres records, NOTIFY announces.** A workflow never writes to the database directly. It calls an activity, which writes the read model and an event row in **one transaction**.

---

## 3. Domain and data model (`fox_mlo` database)

```
customers (cache of Plunet customers)      resources (cache of Plunet PMs)
      │                                           │
orders ─────────────────────────────────────────── pm_resource_id
  id, kind (ORDER|QUOTE), status, number, title, customer_id, pm_resource_id,
  plunet_order_id, plunet_quote_id, deadline, template_id, default_destination,
  source_site, source_lang, temporal_workflow_id, created_at, updated_at
  │
  └── positions
        id, order_id, no, polylang_post_id, source_lang, target_lang,
        plunet_item_id, xliff_raw, xliff_processed, words, segments,
        destination (POLYLANG|ENDPOINT|NONE), destination_url,
        status, temporal_workflow_id, created_at, updated_at
        │
        ├── tasks
        │     id, position_id, seq, type (IMPORT|PM|TRA|REV|QA|DELIVER|…),
        │     status (PENDING|RUNNING|WAITING|DONE|FAILED|SKIPPED|CANCELLED),
        │     plunet_job_id, plunet_job_status, assignee_resource_id,
        │     attempts, cost, currency, started_at, finished_at, error
        │
        └── xliff_segments (kept from v1, re-linked to positions)

workflow_templates   id, name, tasks (ordered list of task types)

events  (the bus + audit log + logs tab)
  id BIGSERIAL, created_at, kind (LOG|STATE|ACTION), level (INFO|WARN|ERROR),
  order_id, position_id, task_id, actor, message, reason, data JSONB
```

- Tasks also store `overlay` (orchestrator-only condition) and `findings` (QA results of the last run, JSONB). Templates have a unique `code` (`standard`, `light`, `regulated`).
- Migrations use **Alembic** (`app/migrations`); the api runs `alembic upgrade head` before starting.
- The v1 tables (`etl_jobs`, `destination_deliveries`) stay read-only until they are removed in the last phase.
- `actor` is free text now (`system`, `plunet`, a PM name). It becomes a user id when login arrives.

---

## 4. Realtime: PostgreSQL as the message bus

### 4.1 Mechanism: events table + `LISTEN/NOTIFY`

`NOTIFY` alone is not durable: a listener that is offline misses messages, and payloads are limited to 8000 bytes. So FOX MLO uses the **transactional outbox** pattern:

1. Every change writes an **`events` row** in the same transaction as the data change.
2. An `AFTER INSERT` trigger calls `pg_notify('fox_events', …)` with a **small** payload (ids only).
3. Postgres delivers `NOTIFY` **only on commit**, so listeners never see an event for data that was rolled back.
4. Listeners that reconnect catch up by reading `events WHERE id > last_seen_id`.

```sql
CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('fox_events', json_build_object(
    'id', NEW.id, 'kind', NEW.kind, 'level', NEW.level,
    'order_id', NEW.order_id, 'position_id', NEW.position_id, 'task_id', NEW.task_id
  )::text);
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER events_notify AFTER INSERT ON events
FOR EACH ROW EXECUTE FUNCTION notify_event();
```

Because the trigger fires for **any** writer (worker activities, api, a manual SQL fix), nobody can forget to publish.

### 4.2 Fan-out to browsers (SSE)

```
worker activity ──INSERT events──► postgres ──NOTIFY fox_events──► api (1 LISTEN conn per process)
                                                                    │ in-memory broadcaster
                                                   ┌────────────────┼────────────────┐
                                             SSE client A     SSE client B     SSE client C
                                        (order 412 page)  (position P05)   (orders list)
```

- Each api process holds **one dedicated** `psycopg` async connection that runs `LISTEN fox_events` (not taken from the request pool).
- A broadcaster forwards each notification to subscribed SSE clients, filtered by scope:
  `GET /api/v1/events/stream?order_id=412` · `?position_id=…` · no filter = the orders list.
- SSE `id:` = `events.id`. On reconnect the browser sends `Last-Event-ID`, and the api replays missed rows from the table, then switches to live.
- Heartbeat comment every 15 s keeps proxies from closing the stream.
- The client receives the small event, then refetches what it needs (or uses `data` for log lines). The UI never trusts only the stream: a refetch on reconnect fixes any gap.

**Why SSE, not WebSocket:** traffic is one-way (server → browser). Commands are normal REST calls. SSE reconnects and resumes on its own and works through the existing reverse proxy.

### 4.3 Channels

| Channel | Payload | Producers | Consumers |
|---|---|---|---|
| `fox_events` | `{id, kind, level, order_id, position_id, task_id}` | `events` trigger | api SSE broadcaster |
| `fox_cache` (optional) | `{entity: "resources"\|"customers"}` | sync activity | api in-memory cache invalidation |

Commands are **not** sent through NOTIFY. They go to Temporal, which is durable and acknowledges them.

### 4.4 Limits to respect

- Keep payloads small (ids only). The 8000-byte limit and one global notification queue make big payloads dangerous.
- `LISTEN` needs a session-level connection: do not put the listener behind PgBouncer in transaction mode.
- Prune or partition `events` (e.g. keep 180 days hot) once volume grows. Analytics reads `tasks`, not `events`.

---

## 5. Workflows with Temporal

### 5.1 Workflow types

| Workflow | ID | Lifetime | Purpose |
|---|---|---|---|
| `OrderWorkflow` | `order-{order_id}` | Until all positions finish or the order is cancelled | Creates the order or quote in Plunet. For a quote, **waits for acceptance**. Then starts one child per position and tracks the summary. |
| `PositionWorkflow` (child) | `position-{position_id}` | One position | Runs the task chain from the template; handles pause, cancel, retry, restart. |
| `PlunetSyncWorkflow` | Schedule `plunet-sync` (every `PLUNET_SYNC_SECONDS`, default 120 s, overlap SKIP); each run is `plunet-sync-run` | Recurring | Reads the status of open jobs and of quotes awaiting acceptance (and their conversion into an order) from Plunet and **signals** the affected workflows. The only sync path from Plunet (no callbacks). |

Task queues: `fox-orchestration` (workflows plus database and Polylang activities) and `fox-plunet` (synchronous SOAP activities on a thread pool, at most `PLUNET_MAX_CONCURRENT_CALLS`, default 4). The worker creates or updates the schedule at start-up.

**Order flow.** `OrderWorkflow` creates the project in Plunet. For an order it starts the positions at once. For a quote it creates the items, imports and uploads each `.xliff`, releases the quote to `PENDING` and waits:
- *accepted* (button, or seen in Plunet by the sync) → FOX MLO sets `ACCEPTED` in Plunet unless it came from there, then waits for the PM to **convert the quote in Plunet** (the SOAP API cannot);
- *converted* (seen by the sync through the quote's `orderID`) → `plunet_adopt_order` finds the order's items by the `FOX-P{position_id}` tag in their description, stores the order number, and the positions start;
- *rejected* (button, or `REJECTED`/`CANCELED`/`EXPIRED` in Plunet) → the order ends as `REJECTED`.

All three signals are idempotent.

### 5.2 PositionWorkflow: task loop

Each task in the template becomes one step. The workflow holds a cursor and a small state machine (simplified; the code is `app/workflows/position.py`):

```python
@workflow.defn
class PositionWorkflow:
    def __init__(self):
        self.cursor = 0
        self.paused = False
        self.cancel_reason: str | None = None
        self.retry_requested = False
        self.restart_from: int | None = None
        self.plunet_status: dict[int, str] = {}   # filled by signals from PlunetSyncWorkflow

    @workflow.run
    async def run(self, inp: PositionInput) -> PositionResult:
        while self.cursor < len(inp.tasks):
            await workflow.wait_condition(lambda: not self.paused or self.cancel_reason)
            if self.cancel_reason:
                return await self._cancel(inp)

            task = inp.tasks[self.cursor]
            ok = await self._run_task(inp, task)          # activities + waits
            if self.restart_from is not None:             # set by an update while running
                self.cursor, self.restart_from = self.restart_from, None
                continue
            if ok:
                self.cursor += 1
                continue
            # Business failure (e.g. QA): stop and wait for a human decision.
            await workflow.wait_condition(
                lambda: self.retry_requested or self.restart_from is not None or bool(self.cancel_reason)
            )
            self.retry_requested = False
        return PositionResult(status="COMPLETED")
```

### 5.3 Task kinds

| Task | Kind | How it runs |
|---|---|---|
| `IMPORT` | automatic | Fetch `.xliff` from Polylang → parse → store segments; create the Plunet item (description `P01 · title · FOX-P{id}`) and upload the file to it. |
| `PM`, `TRA`, `REV` | **human, in Plunet** | Create the Plunet job (job types `PRM`, `TRA`, `REV` on the FOX instance; start = now, due = order deadline, no resource), then **wait** for `plunet_job_status` signals from the sync. `WAITING` while requested or assigned, `RUNNING` while `IN_PROGRESS`; at `DELIVERED` the job price and assignee are read and the task is `DONE`. A job `CANCELED` in Plunet fails the task. When the order deadline passes, one `WARN` event is written. |
| `QA` | automatic | Download the translated `.xliff` from the output folder of the last delivered job (REV, else TRA…), then check every target segment (rules below). A **blocking** finding is a business failure: the task becomes `FAILED` and the workflow waits for Retry, Restart or Cancel. Warnings are logged and shown, but do not stop the workflow. |
| `DELIVER` | automatic | Per destination: `POLYLANG` (create or update the translated post as a draft, linked with `translations[...]`), `ENDPOINT` (POST the file), or `NONE`. Then the Plunet item is set to `DELIVERED`. |

**QA rules (default):**

| Check | Level |
|---|---|
| Empty or missing target | **Blocking** |
| Placeholders differ between source and target (`{0}`, `{name}`, `%s`, `%1$s`, `%d`) | **Blocking** |
| Inline tags differ or are broken (`<g>`, `<x/>`, `<bx/>`, `<ex/>`, `<ph>`) | **Blocking** |
| Target is not well-formed XML | **Blocking** |
| Target identical to source (segments longer than 3 words) | Warning |
| Numbers differ between source and target | Warning |
| Length over `maxwidth` (when the XLIFF sets it) or over 150% of the source (sources of 10+ characters) | Warning |
| Leading or trailing whitespace differs; double spaces | Warning |
| Terminology (glossary) | Later; warning |

**Two kinds of failure:**
- *Technical* (network, SOAP timeout, 5xx): Temporal retries the activity automatically with backoff (e.g. 5 attempts, max 5 min). The UI only shows a WARN log.
- *Business* (QA findings, Plunet rejects input): no automatic retry; the task becomes `FAILED` and needs a user decision.

### 5.4 Controls: how UI actions map to Temporal

All controls are **Workflow Updates**: they are synchronous, validated, and return a result or an error to the UI. Invalid actions are rejected by the update validator, e.g. Resume on a running workflow.

| UI action | Temporal call | Effect |
|---|---|---|
| Pause | update `pause` | `paused = True`; the current task finishes; no new task starts. Human tasks continue in Plunet. |
| Resume | update `resume` | `paused = False`. |
| Retry | update `retry` | Valid only when the current task is `FAILED`; re-runs it (`attempts + 1`). A Plunet task gets a **new** job. |
| Restart from… | update `restart_from(seq, reason?)` | `seq` ≤ current task. An open Plunet job of the current task is cancelled in Plunet first; the tasks from `seq` on are reset to `PENDING` and run again (new Plunet jobs). On a **completed** position the api starts a new `PositionWorkflow` run with `start_from=seq`; attempt counts carry on. |
| Cancel | update `cancel(reason)` | Reason required. Plunet first (open jobs and the item → `CANCELED`), then `CANCELLED` locally. If the Plunet cleanup fails, the cancellation still stands and a `WARN` event asks for a manual check. |
| Accept / reject quote | signals `quote_accepted` / `quote_rejected` on `OrderWorkflow` | From the api (button) **or** from Plunet (detected by `PlunetSyncWorkflow`). Idempotent. Conversion arrives as `quote_converted`. |
| Bulk actions (`pause`, `resume`, `retry_failed`) | api loops over the positions they fit | Same updates per `PositionWorkflow`. |

Every control also writes an `ACTION` event (actor, reason), so it shows in the Logs tab and the activity feed in real time.

### 5.5 State projection

Every state change inside a workflow goes through one activity:

```python
@activity.defn
async def record_task(change: TaskChange) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        ...                                # tasks row (status, attempts, timestamps, job, cost, error, findings)
        ...                                # position status, then the order status recomputed from its positions
        await add_event(session, ...)      # trigger → NOTIFY → SSE
```

Activities must be **idempotent** (Temporal can re-run them): projection writes set absolute values, and every Plunet creation first checks the id already stored in the database and saves the new id in the same activity.

### 5.6 Determinism rules for workflow code

- No I/O, `datetime.now()`, `random` or DB access in workflows. Use activities, `workflow.now()` and `workflow.uuid4()`.
- Changing workflow code that is already running in production uses `workflow.patched()` versioning.
- The Python SDK sandbox runs workflows. Plunet `zeep` calls (synchronous) run in activities on a thread pool executor.

---

## 6. Plunet integration: two-way state sync

**Decision:** Plunet and FOX MLO stay in sync and show the same states. Plunet is the system of record for orders, quotes, items, jobs, assignments and prices. FOX MLO orchestrates and mirrors.

- One `PlunetGateway` (wrapping the existing `plunet_client.py`) used **only** by activities, with session reuse and re-login on expiry.
- Calls used: order or quote creation, item creation per position, job creation per task, job status reads and writes, job price reads, document upload, quote status and the order created from a quote (the SOAP API cannot convert a quote itself; see the implementation plan, "Still open" #3), resource and customer lists.

### 6.1 Shared states

For tasks backed by a Plunet Job (PM, TRA, REV and any other Plunet job type), `tasks.plunet_job_status` stores the **raw Plunet `JobStatus`**. The UI state is derived from it, so both systems always show the same thing:

| Plunet `JobStatus` | FOX MLO task state |
|---|---|
| `IN_PREPERATION` | PENDING |
| `REQUESTED`, `ASSIGNED_WAITING` | WAITING |
| `IN_PROGRESS` | RUNNING |
| `DELIVERED`, `APPROVED` (and the invoice states after it) | DONE |
| `CANCELED` | CANCELLED |
| `OVERDUE` | flag on top of the current state |

Orchestrator-only conditions have no Plunet equivalent, so they are **overlays** shown next to the Plunet state, never written into it:
- `FAILED`: an automatic step failed (e.g. QA).
- `PAUSED`: FOX MLO will not start the next task.

Automatic tasks (IMPORT, QA, DELIVER) have no Plunet job. Their result is written to the Plunet **item** (document upload, item status), so the item status in Plunet matches the position status in FOX MLO.

### 6.2 Direction of changes

| Change made in… | How it reaches the other side |
|---|---|
| **FOX MLO** (create, cancel, restart, assign, accept quote) | The workflow calls a Plunet activity first; the local state is updated only after Plunet confirms. Plunet stays the source of truth. |
| **Plunet** (PM assigns a translator, translator delivers, job cancelled, quote accepted) | **Polling** (`PlunetSyncWorkflow`, every 2 min) reads job, quote and price changes and signals the affected workflows. Plunet callbacks are not used (decision 2026-10-30). |

Signals are idempotent: an unchanged status is ignored.

**Assignments** are made in Plunet by the PM and picked up by the sync. Assigning from FOX MLO (`assign_resource` exists in the gateway) is not exposed yet.

**Conflicts:** Plunet wins: the next sync run signals the Plunet status and the workflow follows it. (No dedicated conflict event yet.)

### 6.3 Cost

Cost comes from **Plunet job prices**. When a job reaches DONE, an activity reads the job price and stores `tasks.cost` + `tasks.currency` (the project currency). Order and analytics totals are sums of these values; analytics reports in the currency most tasks are priced in. FOX MLO does not keep its own rates. Prices changed in Plunet after delivery are not re-read yet.

### 6.4 Limits

The `fox-plunet` task queue limits concurrent SOAP calls (e.g. `max_concurrent_activities=4`).

## 7. Polylang integration

- `SourceConnector` interface (`app/integrations/source.py`): `list_languages()`, `list_posts(lang, search)`, `get_post(id)`, `get_xliff(post_id, target)`, `publish_translation(source, target_lang, title, segments, status="draft")`. Posts carry a word count.
- `POLYLANG_SITE` names the site in the UI (default: the host of `POLYLANG_BASE_URL`); one site per installation for now.
- `PolylangConnector` talks to `polylang-mock` now and to a real WordPress later (URL + application password via env).
- Mock routes: `/wp-json/pll/v1/languages`, `/wp-json/wp/v2/posts?lang=`, `POST /wp-json/wp/v2/posts[/{id}]?lang=&translations[..]=`, plus the mock-only `/wp-json/pll/v1/posts/{id}/xliff?target=`.

---

## 8. API surface (v2)

The contract is the frontend's `services/frontend/src/api/types.ts`; responses are defined in `app/schemas/v2.py`. Details per endpoint: [`api-endpoints.md`](api-endpoints.md).

```
Orders
  GET    /api/v1/orders                    ?kind&status&pm&customer&attention&q&limit&offset
  POST   /api/v1/orders                    create order or quote + positions → starts OrderWorkflow
  GET    /api/v1/orders/{id}               order + positions + tasks + totals
  POST   /api/v1/orders/{id}/accept        quote accepted (signal)
  POST   /api/v1/orders/{id}/reject        {reason?}
  POST   /api/v1/orders/{id}/actions       {action: pause|resume|retry_failed}

Positions / workflows
  GET    /api/v1/positions/{id}            position + tasks + order summary
  POST   /api/v1/positions/{id}/actions    {action: pause|resume|retry|restart_from|cancel, task_seq?, reason?}
  GET    /api/v1/positions/{id}/events     ?level&kind&task_id&after_id&limit
  GET    /api/v1/positions/{id}/segments
  GET    /api/v1/positions/{id}/xliff      ?variant=raw|processed

Events
  GET    /api/v1/events                    ?order_id&position_id&after_id&limit (latest first page)
  GET    /api/v1/events/stream             SSE; ?order_id | ?position_id; Last-Event-ID supported

Reference data
  GET    /api/v1/plunet/customers | /plunet/resources
  GET    /api/v1/templates
  GET    /api/v1/sources/polylang/sites | /languages?site | /posts?site&lang&q

Analytics
  GET    /api/v1/analytics/summary         ?group_by=pm|customer&from&to

Health
  GET    /api/v1/health                    postgres, realtime listener, temporal, polylang, plunet
  GET    /api/v1/health/live               process only (Docker healthcheck)

Dev (DEV_ENDPOINTS=true only)
  /api/v1/dev/…                            create orders, drive the fake Plunet
```

Commands answer `202 Accepted` with the new state. A validator rejection or a finished workflow gives `409 Conflict` with the workflow's message; a missing workflow `404`; invalid input (e.g. cancel without a reason) `422`; Temporal unreachable `503`. Writes take an optional `X-Fox-Actor` header (the actor in the events) until authentication exists.

---

## 9. Key flows

**Create order**
```
UI ─POST /orders─► api: INSERT order+positions (DRAFT) + event ─► start OrderWorkflow(order-412)
OrderWorkflow: create Plunet order ─► create items ─► start PositionWorkflow × N
PositionWorkflow: IMPORT ─► PM (wait on Plunet) ─► TRA ─► REV ─► QA ─► DELIVER
every step: record_task_state ─► events ─► NOTIFY ─► SSE ─► UI updates live
```

**Quote accepted, converted by the PM**
```
UI Accept ─► signal quote_accepted ─► OrderWorkflow sets ACCEPTED in Plunet ─► waits
   (or: quote set to ACCEPTED in Plunet ─► PlunetSyncWorkflow ─► signal quote_accepted(in_plunet))
PM converts the quote in Plunet ─► PlunetSyncWorkflow sees getQuoteObject().orderID ─► signal quote_converted
OrderWorkflow: plunet_adopt_order (items matched by FOX-P tag, kind=ORDER, number) ─► start PositionWorkflows
```

**QA fails, user retries**
```
QA activity returns findings ─► task FAILED + ERROR event ─► UI banner "QA failed"
linguist corrects the file in the job's output folder, user clicks Retry ─► POST /positions/{id}/actions {retry}
api ─► update retry ─► validator OK ─► QA runs again (attempt 2) ─► DONE ─► DELIVER
```

---

## 10. Operations and security

- **Temporal persistence** uses the same Postgres server, in separate databases (`temporal`, `temporal_visibility`). One container to back up. It can be moved to its own server later without code changes.
- **Hosting:** a single VPS runs everything (decision for now). Plan for about 2 GB RAM for Temporal and Postgres together; split them out if load grows.
- **Temporal versions:** server and admin-tools `1.32.1`, UI `2.57.0`, Python SDK `temporalio 1.35.0`. Upgrades go one minor version at a time; the `temporal-setup` job applies schema updates before the server starts.
- **temporal-ui** binds to `127.0.0.1:8088` only; reach it through an SSH tunnel. It must never be exposed through the public proxy.
- **Plunet sync:** polling only (no inbound route from Plunet). If callbacks are added later, they need an HTTPS route protected by a shared secret and an IP allowlist.
- **Temporal namespace:** `fox-mlo`, with workflow history retention of 30 days.
- **Health:** `/health` checks Postgres, the realtime listener, the Temporal connection, Polylang reachability and the Plunet version.
- **Logging:** structured JSON logs from api and worker. Business logs go to `events`, technical logs go to stdout.
- **Secrets:** Plunet and WordPress credentials only in `.env` and the worker environment. The frontend never sees them.
- **Future auth:** the api gets the actor from a dependency (`get_actor()`), which today reads the optional `X-Fox-Actor` header and falls back to `anonymous`. When login is added, it fills `events.actor` and enables per-PM filters, with no changes to workflows.
