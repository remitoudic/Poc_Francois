# System Architecture

FOX MLO orchestrates the translation of WordPress (Polylang) content through Plunet BusinessManager:
**Order → Position → Workflow → Tasks** (Plunet Auftrag or Angebot → Item → Jobs).

This page is the overview. Details: [backend architecture](backend-architecture.md) · [implementation plan and status](backend-implementation-plan.md) · [API endpoints](api-endpoints.md) · [user guide](user-guide.md).

```
  Browser (React, EN/FR)
     │  REST /api/v1  ▲ SSE /events/stream
     ▼                │
  ┌──────────────────────┐   start / signal / update   ┌───────────────────────┐
  │ api (FastAPI)        ├────────────────────────────►│ temporal (1.32.1)     │
  │ commands, queries,   │                             └──────────┬────────────┘
  │ live events          │◄── LISTEN fox_events ──┐               │ task queues
  └──────────┬───────────┘                        │    ┌──────────▼────────────┐
             │ read model                         │    │ worker                │
             ▼                                    │    │ workflows + activities│
  ┌──────────────────────────────────────────┐    │    └───┬──────────────┬────┘
  │ postgres 16                              │◄───┴────────┘ writes +     │
  │ fox_mlo (orders, positions, tasks, events)│     NOTIFY (trigger)      │
  │ temporal, temporal_visibility            │                           │
  └──────────────────────────────────────────┘          SOAP ◄────────────┤──► REST
                                                 Plunet BusinessManager    Polylang / WordPress
                                                 (portal.foxtranslations)  (mock for now)
```

## How it works

1. A project manager creates an order or a quote in the web app: posts × target languages, a workflow template, and where translations go.
2. The api saves it and starts an `OrderWorkflow` in Temporal.
3. The worker creates the order (or quote), one item per position and, task by task, the jobs in Plunet. It imports each `.xliff` from Polylang, runs QA on the translated file and delivers the result.
4. People work in Plunet. Every 2 minutes `PlunetSyncWorkflow` reads job and quote changes and signals the workflows.
5. Every state change is written to Postgres with an event in the same transaction. A trigger announces it with `NOTIFY`, and the api pushes it to browsers over Server-Sent Events.

**Rule:** Temporal decides, Postgres records, NOTIFY announces. Plunet is the source of truth: FOX MLO writes to Plunet first, then mirrors.

## Services (docker-compose)

| Service | Role | Port |
|---|---|---|
| `frontend` | React + Vite app | 3000 |
| `api` | FastAPI: REST, SSE, migrations at start | 8000 |
| `worker` | Temporal workflows and activities (same image as `api`) | – |
| `temporal`, `temporal-setup`, `temporal-namespace` | Workflow engine and its one-shot setup jobs | 7233 (internal) |
| `temporal-ui` | Operations UI | 127.0.0.1:8088 |
| `postgres` | App data, event bus, Temporal persistence | 5433 |
| `polylang-mock` | Stand-in for the WordPress/Polylang REST API | 8090 (internal) |

## Main components

| Component | Where | Notes |
|---|---|---|
| Workflows | `services/backend/app/workflows` | `OrderWorkflow`, `PositionWorkflow`, `PlunetSyncWorkflow` (Schedule) |
| Activities | `services/backend/app/activities` | projection (database), content (Polylang, QA, delivery), plunet (SOAP, idempotent) |
| Plunet gateway | `services/backend/app/integrations/plunet` | SOAP 1.2 via zeep; in-memory fake with `PLUNET_MODE=fake` |
| Polylang connector | `services/backend/app/integrations/polylang.py` | WordPress REST + Polylang |
| XLIFF and QA | `services/backend/app/xliff` | Parser and QA rules |
| API v2 | `services/backend/app/routers`, `app/api`, `app/schemas/v2.py` | Contract shared with `services/frontend/src/api/types.ts` |
| Realtime | `services/backend/app/realtime` | `events` table, LISTEN/NOTIFY, SSE |

The v1 ETL pipeline (`/api/v1/etl`, `/legacy` in the app) still runs and will be removed in phase 7.
