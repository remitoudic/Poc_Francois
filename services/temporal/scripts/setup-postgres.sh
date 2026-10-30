#!/bin/sh
# Create (first run) or upgrade (later runs) the Temporal schemas in Postgres.
# Safe to run on every start.
set -eu

: "${POSTGRES_SEEDS:?POSTGRES_SEEDS is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${SQL_PASSWORD:?SQL_PASSWORD is required}"

PORT="${DB_PORT:-5432}"
SCHEMA_DIR=/etc/temporal/schema/postgresql/v12
sql() { temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" -u "$POSTGRES_USER" -p "$PORT" "$@"; }

echo "Waiting for Postgres at $POSTGRES_SEEDS:$PORT..."
until nc -z -w 5 "$POSTGRES_SEEDS" "$PORT"; do sleep 2; done

setup_db() {
  db="$1"; dir="$2"
  sql --db "$db" create >/dev/null 2>&1 && echo "Created database $db" || echo "Database $db already exists"
  # setup-schema only on an empty database; update-schema brings any version up to date.
  if sql --db "$db" setup-schema -v 0.0 >/dev/null 2>&1; then
    echo "Initialised schema in $db"
  fi
  sql --db "$db" update-schema -d "$SCHEMA_DIR/$dir/versioned"
}

setup_db "${DBNAME:-temporal}" temporal
setup_db "${VISIBILITY_DBNAME:-temporal_visibility}" visibility
echo "Temporal schema setup complete"
