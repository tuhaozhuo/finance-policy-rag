#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose -f deploy/docker-compose.yml up -d --build

echo "Services started. API: http://localhost:8000/api/v1/health"
echo "Runtime profile: prod_qwen (set QWEN_API_BASE/QWEN_API_KEY before startup)"
