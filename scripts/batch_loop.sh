#!/bin/bash

INTERVAL_MIN=${BATCH_INTERVAL_MIN:-60}    # 60min par défaut, 5min en DEV
echo "🔄 MediCore Batch Loop - Intervalle: ${INTERVAL_MIN}min"

# `dbt deps` seulement si packages changent
# Vérifie si dbt_modules/ existe dans le cache
if [ ! -d "/root/.dbt/dbt_modules" ]; then
  echo "📦 dbt deps first run"
  dbt deps --target $ENV                  # Télécharger les packages dbt (dbt_modules/)
fi

while true; do
  echo "🕐 $(date) - Début batch #$(date +%H%M)"

  # 1. CDC batch (Kafka → Snowflake RAW)
  echo "📥 Phase CDC"
  python /app/pipelines/daily_cdc_batch.py

  # 2. dbt pipeline
  echo "🔄 Phase dbt"
#   dbt run --select tag:raw --target $ENV     # pas nécessaire car RAW auto-refresh via views
  dbt run --select tag:staging --target $ENV
  dbt run --select tag:marts --target $ENV
  dbt test --select stg_* --target $ENV

  echo "✅ Batch terminé - Prochain run: $(date -d "+${INTERVAL_MIN} minutes")"
  sleep $((${INTERVAL_MIN} * 60))
done
