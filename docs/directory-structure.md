# Directory Structure

```text
.
├── .github/workflows/deploy.yml        # CI/CD deployment to the VPS
├── docker-compose.yml                  # All services (see architecture.md)
├── env.example                         # Template for .env
├── README.md
├── DESIGN.md                           # Swiss-style design system
├── docs/
│   ├── user-guide.md                   # For project managers
│   ├── architecture.md                 # Overview
│   ├── backend-architecture.md         # Backend design (Temporal, Postgres bus, Plunet sync)
│   ├── backend-implementation-plan.md  # Phases, status, findings, decisions
│   ├── api-endpoints.md
│   └── UX_design_implementation.pdf
├── scripts/
│   ├── start_locally.sh                # Local Docker Compose start
│   └── deploy.sh                       # VPS deployment and health check
├── fixtures/XLIFF/                     # Sample XLIFF files (v1 ETL)
└── services/
    ├── backend/                        # One image, two commands: api and worker
    │   ├── Dockerfile
    │   ├── pyproject.toml              # uv dependencies, Ruff and pytest config
    │   ├── alembic.ini
    │   ├── scripts/plunet_smoke.py     # Manual smoke test against the live Plunet
    │   ├── app/
    │   │   ├── main.py                 # FastAPI app, routers under /api/v1
    │   │   ├── worker.py               # Temporal workers + Plunet sync schedule
    │   │   ├── config.py               # Settings (env)
    │   │   ├── database.py             # Sync (v1) and async (v2) SQLAlchemy sessions
    │   │   ├── domain/                 # Enums, Plunet status mapping
    │   │   ├── models/                 # Tables: orchestration.py (v2), job.py (v1 + segments)
    │   │   ├── migrations/             # Alembic
    │   │   ├── workflows/              # OrderWorkflow, PositionWorkflow, PlunetSyncWorkflow, dev, payloads
    │   │   ├── activities/             # projection, content (Polylang, QA, delivery), plunet
    │   │   ├── integrations/           # plunet/ (SOAP gateway + fake), polylang.py, source.py, errors.py
    │   │   ├── xliff/                  # XLIFF parser and QA rules
    │   │   ├── realtime/               # events table, LISTEN/NOTIFY listener, SSE broadcaster
    │   │   ├── temporal/               # Shared Temporal client
    │   │   ├── api/                    # v2 dependencies and read-model views
    │   │   ├── schemas/                # v2.py (API contract), job.py (v1)
    │   │   ├── routers/                # orders, positions, reference, analytics, events, health, dev; v1: etl, xliff, plunet
    │   │   └── services/               # v1 ETL services (removed in phase 7)
    │   └── tests/                      # pytest: unit, workflows (time-skipping), API (Postgres test DB)
    ├── frontend/                       # React + TypeScript + Vite
    │   └── src/
    │       ├── main.tsx                # Routes
    │       ├── api/                    # Contract (types.ts), HTTP client, mock API
    │       ├── pages/                  # Orders, NewOrder, OrderDetail, Workflow, Analytics
    │       ├── components/  hooks/  i18n/ (en, fr)
    │       └── App.tsx                 # v1 dashboard, served at /legacy
    ├── polylang-mock/                  # Mock WordPress/Polylang REST API with seed data
    ├── temporal/                       # Temporal server and admin-tools images, setup scripts
    └── db/                             # PostgreSQL image and init.sql
```
