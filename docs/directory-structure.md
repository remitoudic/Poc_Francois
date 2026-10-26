# Directory Structure

```text
.
├── docker-compose.yml              # Multi-container orchestration
├── env.example                     # Template for environment variables
├── README.md
├── DESIGN.md                       # Swiss-style design system
├── docs/                           # Project documentation
├── fixtures/                       # Sample XLIFF test files
│   └── XLIFF/
│       ├── example.de-AT.xlf       # German (Austria) sample
│       └── example.fr.xlf          # French sample
└── services/
    ├── backend/                    # FastAPI backend service
    │   ├── Dockerfile
    │   ├── pyproject.toml          # UV dependencies & Ruff config
    │   ├── uv.lock
    │   ├── test_connection.py      # Standalone Plunet connectivity & auth tester
    │   ├── plunet_client.py        # Plunet SOAP API client wrapper
    │   ├── examples.py             # Usage examples (Zeep & pyplunet)
    │   └── app/
    │       ├── main.py             # FastAPI entry point & lifespan
    │       ├── config.py           # Pydantic settings
    │       ├── database.py         # SQLAlchemy & DB connection
    │       ├── models/             # Database tables (ETLJob, XLIFFSegment, ...)
    │       ├── schemas/            # Request/response Pydantic schemas
    │       ├── routers/            # Routes (/health, /etl, /xliff, /plunet)
    │       └── services/           # XLIFF parser, Plunet service, dispatcher
    ├── frontend/                   # React web application
    │   ├── Dockerfile
    │   ├── package.json
    │   ├── vite.config.ts
    │   ├── index.html
    │   └── src/
    │       ├── App.tsx             # Dashboard & job detail page
    │       ├── App.css
    │       └── main.tsx
    └── db/                         # PostgreSQL service
        ├── Dockerfile
        └── init.sql                # Initial schema & extensions
```
