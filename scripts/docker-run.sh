#!/bin/bash
# Usage: ./scripts/docker-run.sh [dev|prod]

ENV=${1:-dev}
COMPOSE_FILE="docker-compose.yml"

echo "🐳 Docker MediCore - ENV: $ENV"
docker-compose down -v
docker-compose build --no-cache

# Lancer avec env vars
docker-compose \
  --env-file .env \
  --profile $ENV \
  up --build medicore-etl

echo "✅ Pipeline terminé. Logs dans ./logs/"
