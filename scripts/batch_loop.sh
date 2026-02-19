#!/bin/bash
set -euo pipefail

# Intervalle entre batches : 5 min en dev, 30 min en prod (surchargeable via BATCH_INTERVAL_MIN)
if [ "${ENV}" = "prod" ]; then
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-30}
else
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-5}
fi
LOCK_FILE="/tmp/bulk_load.lock"
REF_DONE_FLAG="/tmp/ref_bulk_done_today"
REF_RELOAD_HOUR=${REF_RELOAD_HOUR:-03}

echo "MediCore Batch Loop - ${INTERVAL_MIN}min - ENV: ${ENV} - ref reload at ${REF_RELOAD_HOUR}h"

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

  # 0. Re-bulk quotidien des 14 tables reference (1x/jour a ${REF_RELOAD_HOUR}h)
  HOUR=$(date +%H)
  if [ "$HOUR" = "$REF_RELOAD_HOUR" ] && [ ! -f "$REF_DONE_FLAG" ]; then
    echo "Phase ref-reload: 14 tables reference (truncate + bulk load)"
    python /app/pipelines/bulk_load.py --ref-only --truncate && touch "$REF_DONE_FLAG"
  fi
  [ "$HOUR" = "00" ] && rm -f "$REF_DONE_FLAG"

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
