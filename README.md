# FOX MLO — Translation ETL & Plunet BusinessManager Orchestrator

[![Docker Compose](https://img.shields.io/badge/Docker_Compose-v2+-blue.svg?logo=docker)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Astral UV](https://img.shields.io/badge/Package_Manager-uv_0.6.5-purple.svg)](https://github.com/astral-sh/uv)
[![React](https://img.shields.io/badge/Frontend-React_19_+_Vite-61DAFB.svg?logo=react)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Plunet](https://img.shields.io/badge/Plunet-v10.26.2_SOAP_API-orange.svg)](https://portal.foxtranslations.com/)

**FOX MLO** is an end-to-end Machine Learning Operations & ETL pipeline designed to extract XLIFF translation files from external APIs and client repositories, parse & validate segments, calculate metrics (word counts, placeholder preservation), synchronize projects with **Plunet BusinessManager** via SOAP 1.2 web services, and transport processed payloads to destination servers.

---

## 1. System Architecture

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

### Key Components

* **Frontend Dashboard (`services/frontend`)**: React + TypeScript + Vite app displaying **"Welcome to FOX MLO"**, live connectivity badges, pipeline runner, segment inspection, and destination delivery feeds.
* **Backend Service (`services/backend`)**: High-performance FastAPI server packaged with **Astral `uv`**, with modular `APIRouter` endpoints for ETL, XLIFF operations, Plunet integration, and health checks.
* **Database (`services/db`)**: PostgreSQL 16 container storing execution jobs, parsed translation segments, word counts, and delivery receipts.
* **Plunet Integration**: Direct SOAP 1.2 client (`zeep` / `pyplunet`) connecting to `https://portal.foxtranslations.com/` (tested against version 10.26.2).

---

## 2. Directory Structure

```text
.
├── docker-compose.yml              # Multi-container orchestration
├── .env.example                    # Template for environment variables
├── README.md
├── fixtures/                       # Sample XLIFF test files
│   └── XLIFF/
│       ├── example.de-AT.xlf       # German (Austria) sample
│       └── example.fr.xlf          # French sample
└── services/
    ├── backend/                    # FastAPI Backend Service
    │   ├── Dockerfile
    │   ├── pyproject.toml          # UV project dependencies & Ruff config
    │   ├── uv.lock
    │   ├── test_connection.py      # Standalone Plunet connectivity & auth tester
    │   ├── plunet_client.py        # Plunet SOAP API client wrapper
    │   ├── examples.py             # Usage examples (Zeep & pyplunet)
    │   └── app/
    │       ├── main.py             # FastAPI entry point & lifespan
    │       ├── config.py           # Pydantic settings
    │       ├── database.py         # SQLAlchemy & DB connection
    │       ├── models/             # Database tables (ETLJob, XLIFFSegment, etc.)
    │       ├── schemas/            # Request/Response Pydantic schemas
    │       ├── routers/            # Modular routes (/health, /etl, /xliff, /plunet)
    │       └── services/           # XLIFF parser, Plunet service, Dispatcher
    ├── frontend/                   # React Web Application
    │   ├── Dockerfile
    │   ├── package.json
    │   ├── vite.config.ts
    │   ├── index.html
    │   └── src/
    │       ├── App.tsx             # Main Dashboard ("Welcome to FOX MLO")
    │       ├── App.css
    │       └── main.tsx
    └── db/                         # PostgreSQL Service
        ├── Dockerfile
        └── init.sql                # Initial schema & extensions setup
```

---

## 3. Quick Start (Docker Compose)

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/) installed on your machine.

### 1. Clone & Configure Environment
```bash
git clone https://github.com/remitoudic/Poc_Francois.git
cd Poc_Francois

cp env.example .env
```

Verify your credentials in `.env`:
```ini
# Plunet BusinessManager API
PLUNET_BASE_URL=https://portal.foxtranslations.com/
PLUNET_USERNAME=API integration
PLUNET_PASSWORD=your_password

# PostgreSQL Database Configuration
POSTGRES_USER=fox_user
POSTGRES_PASSWORD=fox_password
POSTGRES_DB=fox_mlo
POSTGRES_PORT=5432
POSTGRES_HOST_PORT=5433
DATABASE_URL=postgresql+psycopg://fox_user:fox_password@postgres:5432/fox_mlo

# Destination Server (default mock receiver)
DEFAULT_DESTINATION_URL=http://backend:8000/api/v1/etl/simulate-destination
```

### 2. Build & Launch Containers
```bash
docker compose up -d --build
```

### 3. Verify Container Status
```bash
docker compose ps
```

Expected output:
```text
NAME               IMAGE             STATUS                    PORTS
fox_mlo_frontend   plunet-frontend   Up (healthy)              0.0.0.0:3000->3000/tcp
fox_mlo_backend    plunet-backend    Up (healthy)              0.0.0.0:8000->8000/tcp
fox_mlo_postgres   plunet-postgres   Up (healthy)              0.0.0.0:5433->5432/tcp
```

---

## 4. Web Dashboard & API Access

| Service | URL | Description |
|---|---|---|
| **Frontend UI** | [http://localhost:3000](http://localhost:3000) | **"Welcome to FOX MLO"** Dashboard |
| **FastAPI Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API documentation |
| **System Health Check** | [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) | Live DB & Plunet connectivity status |
| **PostgreSQL Database** | `localhost:5433` | Database: `fox_mlo`, User: `fox_user` |

---

## 5. API Endpoints

### Health & Status
* `GET /api/v1/health`: Checks FastAPI, PostgreSQL DB status, and queries Plunet server version.

### ETL Pipeline (`/api/v1/etl`)
* `POST /api/v1/etl/run`: Executes full end-to-end pipeline:
  1. **Extract:** Reads XLIFF from remote API, upload, or fixture (`example.fr.xlf`, `example.de-AT.xlf`).
  2. **Transform:** Parses `<trans-unit>` segments, validates placeholder tags (`{0}`, `%s`), and counts words.
  3. **Plunet Sync:** Authenticates to Plunet SOAP API, obtains session UUID, registers project/order reference.
  4. **Destination Dispatch:** Transports transformed payload via HTTP POST to the destination server.
* `GET /api/v1/etl/jobs`: Lists all historical ETL jobs.
* `GET /api/v1/etl/jobs/{job_id}`: Retrieves full details of a specific job, including extracted segments and XML.
* `POST /api/v1/etl/simulate-destination`: Built-in mock receiver endpoint for destination servers.
* `GET /api/v1/etl/destination-deliveries`: Lists all payloads delivered to the mock destination server.

### XLIFF Tools (`/api/v1/xliff`)
* `GET /api/v1/xliff/fixtures`: Lists sample XLIFF files with word counts and language pairs.
* `GET /api/v1/xliff/fixtures/{filename}`: Parses and inspects a sample file.
* `POST /api/v1/xliff/upload`: Uploads and parses an external XLIFF file.

### Plunet BusinessManager SOAP Integration (`/api/v1/plunet`)
* `GET /api/v1/plunet/status`: Fetches live version (`10.26.2`) from `portal.foxtranslations.com`.
* `POST /api/v1/plunet/test-login`: Authenticates with Plunet credentials and retrieves a live session UUID.

---

## 6. Local Development with `uv`

The backend uses **Astral `uv`** for dependency resolution and Python tooling:

```bash
cd services/backend

# Install dependencies into virtual environment
uv sync

# Run code linter
uv run ruff check app

# Auto-format code
uv run ruff format app

# Test live Plunet SOAP API connection
uv run python test_connection.py

# Run standalone Plunet examples
uv run python examples.py

# Run local FastAPI server with reload
uv run uvicorn app.main:app --reload --port 8000
```

---

## 7. License

Proprietary &bull; Fox Translations
