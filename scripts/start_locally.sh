#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root directory regardless of where the script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "============================================================"
echo " FOX MLO — Local Environment Startup"
echo "============================================================"

# 1. Verify Docker & Docker Compose availability
if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[ERROR] Docker daemon is not running. Please start Docker Desktop and try again." >&2
  exit 1
fi

# 2. Ensure .env configuration exists
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
  if [ -f "${PROJECT_ROOT}/env.example" ]; then
    cp "${PROJECT_ROOT}/env.example" "${PROJECT_ROOT}/.env"
    echo "[INFO] Created .env from env.example."
    echo "[WARN] Please update PLUNET_USERNAME and PLUNET_PASSWORD in .env with your Plunet credentials."
  else
    echo "[ERROR] Neither .env nor env.example found in ${PROJECT_ROOT}." >&2
    exit 1
  fi
else
  echo "[INFO] Using existing .env configuration."
fi

# 3. Build and start containers
echo "[INFO] Building and starting Docker Compose stack..."
docker compose up -d --build "$@"

# 4. Wait for backend health check
BACKEND_PORT="${BACKEND_HOST_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_HOST_PORT:-3000}"
POSTGRES_PORT="${POSTGRES_HOST_PORT:-5433}"

echo "[INFO] Waiting for backend service to become healthy on port ${BACKEND_PORT}..."
MAX_RETRIES=30
RETRY_COUNT=0
until curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ "${RETRY_COUNT}" -ge "${MAX_RETRIES}" ]; then
    echo "[WARN] Backend health check did not respond within ${MAX_RETRIES}s. Check logs with: docker compose logs backend"
    break
  fi
  sleep 1
done

echo ""
docker compose ps
echo ""
echo "============================================================"
echo " Services are running:"
echo "  - Frontend UI:      http://localhost:${FRONTEND_PORT}"
echo "  - Backend Swagger:  http://localhost:${BACKEND_PORT}/docs"
echo "  - Health Check:     http://localhost:${BACKEND_PORT}/api/v1/health"
echo "  - PostgreSQL:       localhost:${POSTGRES_PORT}"
echo "============================================================"
