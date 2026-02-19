#!/bin/bash
set -euo pipefail

# Intervalle entre batches : 5 min en dev, 30 min en prod (surchargeable via BATCH_INTERVAL_MIN)
if [ "${ENV}" = "prod" ]; then
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-30}
else
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-5}
fi
LOCK_FILE="/tmp/bulk_load.lock"

echo "MediCore Batch Loop - ${INTERVAL_MIN}min - ENV: ${ENV}"

# En dev : mode single-run (pas de boucle infinie)
if [ "${ENV}" = "dev" ] && [ "${BATCH_LOOP:-true}" = "false" ]; then
  echo "Dev mode: boucle desactivee (BATCH_LOOP=false). Lancer manuellement chaque composant."
  exit 0
fi

while true; do
  echo "$(date) - Debut batch #$(date +%H%M)"

  # Verifier qu'un bulk load n'est pas en cours
  if [ -f "$LOCK_FILE" ]; then
    echo "Bulk load en cours (lock: $LOCK_FILE) - batch skippe"
    sleep $((INTERVAL_MIN * 60))
    continue
  fi

  # 1. CDC (Kafka -> Snowflake RAW)
  echo "Phase CDC"
  python /app/pipelines/daily_cdc_batch.py || echo "CDC skipped (no new data)"

  # 2. DBT pipeline
  echo "Phase dbt"
  cd /app/dbt
  dbt run --select tag:staging --target $ENV || echo "Staging skipped"
  dbt run --select tag:marts --target $ENV || echo "Marts skipped"
  dbt test --select stg_* --target $ENV || echo "Tests skipped"
  cd /app

  echo "Batch termine - Prochain run: $(date -d "+${INTERVAL_MIN} minutes" 2>/dev/null || echo "${INTERVAL_MIN}min")"
  sleep $((INTERVAL_MIN * 60))
done
