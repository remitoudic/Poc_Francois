# API Endpoints

Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Health & Status
* `GET /api/v1/health`: Checks PostgreSQL, the realtime listener, Temporal, Polylang and the Plunet server version.
* `GET /api/v1/health/live`: Liveness only (used by Docker healthchecks).

## Realtime (`/api/v1/events`)
* `GET /api/v1/events/stream`: Server-Sent Events of the events bus. Optional `order_id` or `position_id` scope. Resumes after `Last-Event-ID` (header) or `last_event_id` (query). Sends `event: resync` when the server may have missed events; the client should refetch.
* `GET /api/v1/events`: Event history. Query: `order_id`, `position_id`, `after_id`, `limit`.

## System (`/api/v1/system`)
* `POST /api/v1/system/check-workflow`: Runs a Temporal workflow that writes one event, to check the round trip api → Temporal → worker → Postgres → SSE.

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
