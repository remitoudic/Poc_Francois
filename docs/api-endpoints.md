# API Endpoints

Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Health & Status
* `GET /api/v1/health`: Checks FastAPI and PostgreSQL status, and queries the Plunet server version.

## ETL Pipeline (`/api/v1/etl`)
* `POST /api/v1/etl/run`: Runs the full pipeline (Extract → Validate → Process → Deliver).
  * Body fields: `source_type`, `fixture_name`, `api_url`, `workflow_type`, `destination_url`, `sync_with_plunet`, `job_name`.
* `GET /api/v1/etl/jobs`: Lists all ETL jobs.
* `GET /api/v1/etl/jobs/{job_id}`: Returns one job with its segments, raw XLIFF and processed XLIFF.
* `POST /api/v1/etl/simulate-destination`: Built-in mock receiver for destination servers.
* `GET /api/v1/etl/destination-deliveries`: Lists payloads received by the mock destination.

## XLIFF Tools (`/api/v1/xliff`)
* `GET /api/v1/xliff/fixtures`: Lists sample XLIFF files with word counts and language pairs.
* `GET /api/v1/xliff/fixtures/{filename}`: Parses and inspects a sample file.
* `POST /api/v1/xliff/upload`: Uploads and parses an external XLIFF file.

## Plunet BusinessManager (`/api/v1/plunet`)
* `GET /api/v1/plunet/status`: Returns the live Plunet version from `portal.foxtranslations.com`.
* `POST /api/v1/plunet/test-login`: Logs in with the configured credentials and returns a session UUID.
