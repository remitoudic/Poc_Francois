#!/usr/bin/env bash
# deploy.sh — Deploy FOX MLO to VPS (Docker Compose + Nginx Virtual Host)
# Usage: bash scripts/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

REQUIRED_VARS=(POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB PLUNET_BASE_URL)
BACKEND_PORT="${BACKEND_HOST_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_HOST_PORT:-3000}"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     FOX MLO — Production VPS Deploy                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Environment pre-flight ──────────────────────────────────────────
echo "▶ Step 1/5 — Environment pre-flight"
if [ ! -f .env ]; then
  echo "  ERROR: .env file not found in ${PROJECT_ROOT}." >&2
  exit 1
fi

missing_vars=()
for var in "${REQUIRED_VARS[@]}"; do
  if ! grep -E -q "^${var}=" .env; then
    missing_vars+=("$var")
  fi
done
if [ ${#missing_vars[@]} -gt 0 ]; then
  echo "  ERROR: Missing required variables in .env: ${missing_vars[*]}" >&2
  exit 1
fi
echo "  OK — All required environment variables present."

# ── Step 2: Git pull (sync main) ────────────────────────────────────────────
echo ""
echo "▶ Step 2/5 — Syncing Git repository"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
if [ "${SKIP_GIT_PULL:-false}" = "true" ]; then
  echo "  SKIP — SKIP_GIT_PULL is set."
elif [ -d .git ]; then
  git fetch origin
  git checkout -B "${DEPLOY_BRANCH}" "origin/${DEPLOY_BRANCH}"
  git reset --hard "origin/${DEPLOY_BRANCH}"
  echo "  OK — Code updated to origin/${DEPLOY_BRANCH} ($(git rev-parse --short HEAD))."
else
  echo "  SKIP — Not a git repository."
fi

# ── Step 3: Build & restart containers ──────────────────────────────────────
echo ""
echo "▶ Step 3/5 — Building and starting Docker Compose services"
docker compose up -d --build --remove-orphans
echo "  OK — Containers started."

# ── Step 4: Ensure Nginx Virtual Host for 147.93.111.113 ────────────────────
echo ""
echo "▶ Step 4/5 — Verifying Nginx reverse proxy configuration"
NGINX_CID=$(docker ps -qf "name=jobwizard_nginx" | head -n 1 || true)
if [ -n "${NGINX_CID}" ]; then
  if ! docker exec "${NGINX_CID}" test -f /etc/nginx/conf.d/plunet.conf; then
    echo "  Restoring /etc/nginx/conf.d/plunet.conf in ${NGINX_CID}..."
    docker exec -i "${NGINX_CID}" sh -c "cat > /etc/nginx/conf.d/plunet.conf" << 'EOF'
server {
    listen 80;
    listen [::]:80;

    server_name 147.93.111.113;

    client_max_body_size 50M;

    location /api/ {
        proxy_pass http://172.20.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /docs {
        proxy_pass http://172.20.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://172.20.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://172.20.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF
    docker exec "${NGINX_CID}" nginx -t && docker exec "${NGINX_CID}" nginx -s reload
  fi
  echo "  OK — Nginx virtual host (plunet.conf) active."
else
  echo "  WARN — jobwizard_nginx container not found; skipping Nginx vhost check."
fi

# ── Step 5: Health check verification ───────────────────────────────────────
echo ""
echo "▶ Step 5/5 — Health check verification"
MAX_RETRIES=30
RETRY_COUNT=0
until curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ "${RETRY_COUNT}" -ge "${MAX_RETRIES}" ]; then
    echo "  ERROR: Backend health check failed after ${MAX_RETRIES}s." >&2
    docker compose logs --tail 50 api worker temporal || true
    exit 1
  fi
  sleep 2
done

echo "  OK — Backend is healthy."
echo ""
docker compose ps
echo ""
echo "Deployment complete: http://147.93.111.113"
