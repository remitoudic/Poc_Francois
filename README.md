# FOX MLO — Translation ETL & Plunet Orchestrator

**FOX MLO** extracts XLIFF translation files, validates and processes them, syncs them with **Plunet BusinessManager** (SOAP 1.2), and delivers the result to destination servers.

Stack: FastAPI (uv) · React + Vite · PostgreSQL 16 · Docker Compose

## Quick Start (Docker Compose)

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)

### 1. Clone & configure
```bash
git clone https://github.com/remitoudic/Poc_Francois.git
cd Poc_Francois
cp env.example .env
```

Fill in your credentials in `.env`:
```ini
PLUNET_BASE_URL=https://portal.foxtranslations.com/
PLUNET_USERNAME=<your-plunet-user>
PLUNET_PASSWORD=<your-plunet-password>

POSTGRES_USER=fox_user
POSTGRES_PASSWORD=fox_password
POSTGRES_DB=fox_mlo
POSTGRES_HOST_PORT=5433
```

### 2. Build & launch
```bash
docker compose up -d --build
docker compose ps
```

### 3. Open
| Service | URL |
|---|---|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| API docs (Swagger) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) |
| PostgreSQL | `localhost:5433` |

## Documentation
* [System Architecture](docs/architecture.md)
* [Directory Structure](docs/directory-structure.md)
* [API Endpoints](docs/api-endpoints.md)
* [Design System](DESIGN.md)
