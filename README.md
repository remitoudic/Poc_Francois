# FOX MLO — Translation workflow orchestrator

**FOX MLO** takes posts and pages from a WordPress site (Polylang), runs them through **Plunet BusinessManager** for translation and review, checks the result automatically, and puts the translations back on the site. Project managers follow every order, position and task in one place, live.

Stack: FastAPI (uv) · Temporal · PostgreSQL 16 · React + Vite · Docker Compose

## Quick start (Docker Compose)

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/) and Docker Compose

### 1. Clone and configure
```bash
git clone https://github.com/remitoudic/Poc_Francois.git
cd Poc_Francois
cp env.example .env
```

Fill in `.env` (see `env.example` for every setting):
```ini
PLUNET_BASE_URL=https://portal.foxtranslations.com/
PLUNET_USERNAME=<your-plunet-user>
PLUNET_PASSWORD=<your-plunet-password>
PLUNET_MODE=soap            # or "fake": in-memory Plunet for local development

POSTGRES_USER=fox_user
POSTGRES_PASSWORD=fox_password
POSTGRES_DB=fox_mlo
POSTGRES_HOST_PORT=5433
```

### 2. Build and start
```bash
./scripts/start_locally.sh
```
*(or `docker compose up -d --build`)*

### 3. Open
| Service | URL |
|---|---|
| App | [http://localhost:3000](http://localhost:3000) |
| API docs (Swagger) | [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) |
| Health check | [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) |
| Temporal UI | [http://localhost:8088](http://localhost:8088) (local only) |
| PostgreSQL | `localhost:5433` |

The app runs on demo data in the browser until it is connected to the API (phase 6). To try it against the real backend, run the frontend with `VITE_API_MODE=http npm run dev` in `services/frontend` (the Docker setup gets this switch in phase 6).

## Local development without Plunet

```bash
PLUNET_MODE=fake DEV_ENDPOINTS=true PLUNET_SYNC_SECONDS=15 POLYLANG_SITE=maison-lumiere.com \
  docker compose up -d --force-recreate api worker
```
The fake Plunet lives in the worker's memory (restarting the worker clears it). The `/api/v1/dev` endpoints create orders and play the PM or translator; see [API endpoints](docs/api-endpoints.md#dev-apiv1dev-only-with-dev_endpointstrue). Never enable `DEV_ENDPOINTS` in production.

## Tests

```bash
cd services/backend
uv run python -m pytest        # unit, workflow and API tests
uv run ruff check app tests
```
The API tests create and migrate a `fox_mlo_test` database on `localhost:5433` (override with `TEST_DATABASE_URL`) and are skipped if Postgres is not running. `uv run python scripts/plunet_smoke.py --customer-id <id> --pm-id <id> [--quote]` checks the live Plunet portal: it creates test objects and deletes them afterwards.

## Documentation
* [User guide](docs/user-guide.md) — for project managers
* [System architecture](docs/architecture.md) — overview
* [Backend architecture](docs/backend-architecture.md) — workflows, realtime, Plunet sync
* [Implementation plan and status](docs/backend-implementation-plan.md)
* [API endpoints](docs/api-endpoints.md)
* [Directory structure](docs/directory-structure.md)
* [Design system](DESIGN.md)
