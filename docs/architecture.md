# System Architecture

```
[ External Translation APIs / Fixtures ]
                   │
                   ▼ (1. Extract XLIFF)
       ┌───────────────────────┐
       │     FastAPI (UV)      │ ── (Store & Track) ──► [ PostgreSQL 16 ]
       │  Backend (Port 8000)  │
       └───────────┬───────────┘
                   │
      ┌────────────┴────────────┐
      ▼ (2. Load & Sync)        ▼ (3. Transport & Deliver)
[ Plunet BusinessManager ]    [ Destination Servers / Webhooks ]
(portal.foxtranslations.com)
```

## Pipeline Phases

| Phase | Name | Description |
|---|---|---|
| 01 | **EXTRACT** | Acquire XLIFF from an external API or a local fixture |
| 02 | **VALIDATE** | Parse `<trans-unit>` segments, validate placeholder tags (`{0}`, `%s`), count words |
| 03 | **PROCESS** | Authenticate to the Plunet SOAP API and register the project/order |
| 04 | **DELIVER** | Transport the processed payload to the selected destination server |

## Key Components

* **Frontend (`services/frontend`)**: React + TypeScript + Vite dashboard with the pipeline runner, the jobs table, and the job detail page.
* **Backend (`services/backend`)**: FastAPI server managed with **Astral `uv`**. Uses modular `APIRouter` endpoints for ETL, XLIFF, Plunet and health checks.
* **Database (`services/db`)**: PostgreSQL 16. Stores ETL jobs, parsed segments, word counts and delivery receipts.
* **Plunet integration**: SOAP 1.2 client (`zeep` / `pyplunet`) that connects to `https://portal.foxtranslations.com/` (tested against v10.26.2).
