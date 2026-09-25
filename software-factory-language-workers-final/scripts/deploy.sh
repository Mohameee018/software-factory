#!/usr/bin/env bash
set -euo pipefail
[ -f .env ] || cp .env.example .env
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }

echo 'Validating Compose configuration...'
docker compose config >/dev/null

echo 'Building production images...'
docker compose build

echo 'Starting bot and language workers...'
docker compose up -d

echo 'Service status:'
docker compose ps

echo 'Health snapshot:'
docker compose exec -T bot factory health || true
