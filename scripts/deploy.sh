#!/bin/sh
# Pull latest main and restart the prod stack.
# Intended to be run inside a GitHub Codespace (or any box with docker + this repo).
#
# Usage:  ./scripts/deploy.sh
set -eu

cd "$(dirname "$0")/.."

echo ">> git pull"
git pull --ff-only

echo ">> ensuring .env.prod exists"
if [ ! -f .env.prod ]; then
  echo "ERROR: .env.prod not found. Copy .env.prod.example and fill in real values first." >&2
  exit 1
fi

echo ">> docker compose up (build + recreate changed services)"
docker compose -f docker-compose.prod.yml up -d --build

echo ">> running migrations (idempotent)"
docker compose -f docker-compose.prod.yml run --rm migrate || true

echo ">> status"
docker compose -f docker-compose.prod.yml ps

echo ">> done"
