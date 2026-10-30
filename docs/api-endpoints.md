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

## Orders (`/api/v1/orders`)
* `GET /api/v1/orders`: `?kind&status&pm&customer&attention&q&limit&offset`, newest first.
* `POST /api/v1/orders`: Creates an order or quote (one position per post × target language) and starts its workflow. 201 with the order; 422 on invalid input; 503 if the workflow could not start (the order is kept as `DRAFT`).
* `GET /api/v1/orders/{id}`: Order with positions, tasks and totals.
* `POST /api/v1/orders/{id}/accept` · `/reject` (body: `reason`, optional): Open quotes only, else 409.
* `POST /api/v1/orders/{id}/actions`: `{action: pause | resume | retry_failed}` on every position it fits.

## Positions (`/api/v1/positions`)
* `GET /api/v1/positions/{id}`: Position with its tasks and a summary of its order.
* `POST /api/v1/positions/{id}/actions`: `{action: pause | resume | retry | restart_from | cancel, task_seq?, reason?}`. 202 with the position; 409 when the workflow refuses (message from the workflow), 422 for a cancel without reason or a missing `task_seq`.
* `GET /api/v1/positions/{id}/events`: `?level&kind&task_id&after_id&limit`.
* `GET /api/v1/positions/{id}/segments`: Source, target and QA findings per unit.
* `GET /api/v1/positions/{id}/xliff`: `?variant=raw|processed`, as a file download.

## Events (`/api/v1/events`)
* `GET /api/v1/events`: `?order_id&position_id&after_id&limit`. Without `after_id`, the latest `limit` events, oldest first.
* `GET /api/v1/events/stream`: Server-Sent Events, `?order_id | ?position_id`, resumes from `Last-Event-ID`.

## Reference data
* `GET /api/v1/plunet/customers` · `/plunet/resources`: Active customers and project managers from Plunet (FOX MLO ids).
* `GET /api/v1/templates`: Workflow templates and their tasks.
* `GET /api/v1/sources/polylang/sites` · `/languages?site` · `/posts?site&lang&q`.

## Analytics
* `GET /api/v1/analytics/summary`: `?group_by=pm|customer&from&to`.

All write calls take an optional `X-Fox-Actor` header (the name shown in the logs) until authentication exists.

## Dev (`/api/v1/dev`, only with `DEV_ENDPOINTS=true`)
Temporary until the v2 API (phase 5). Never enabled in production.
* `POST /api/v1/dev/orders`: Creates an order or quote (`kind`, `template`, `positions[]` with `post_id`, `title`, `target_lang`) and starts its `OrderWorkflow`.
* `POST /api/v1/dev/orders/{order_id}/accept` · `/reject`: Accepts or rejects a quote (body: `actor`, `reason`).
* `POST /api/v1/dev/positions/{position_id}/{action}`: `pause`, `resume`, `retry`, `cancel` (reason required) or `restart` (body: `seq`). Returns 409 with the reason when the workflow refuses.
* `GET /api/v1/dev/positions/{position_id}/state`: The workflow's own view of the position.
* With `PLUNET_MODE=fake` only: `POST /api/v1/dev/plunet/jobs/{job_id}/status` (body: `status`, `resource_plunet_id`), `POST /api/v1/dev/plunet/quotes/{order_id}/convert`, `POST /api/v1/dev/plunet/sync`. Each change goes into the fake Plunet and reaches the workflow through the sync, as in production.
