#!/bin/bash
set -euo pipefail

INTERVAL_MIN=${BATCH_INTERVAL_MIN:-5}
echo "🚀 MediCore Batch Loop - ${INTERVAL_MIN}min - ENV: $ENV"

# # DBT first run
# if [ ! -d "/root/.dbt/dbt_modules" ]; then
#   echo "📦 dbt deps first run"
#   cd /app/dbt
#   DBT_PROFILES_DIR=/app dbt deps --target $ENV || echo "⚠️ dbt deps skipped"
# fi
# pas necessaire pas de package externe (pas de packages.yml)
# si packages.yml existe alors installer git dans Docker via Dockerfile

while true; do
  echo "🕐 $(date) - Début batch #$(date +%H%M)"
  
  # 1. CDC (Kafka → Snowflake RAW)
  echo "📥 Phase CDC"
  python /app/pipelines/daily_cdc_batch.py || echo "⚠️ CDC skipped (no new data)"
  
  # 2. DBT pipeline
  echo "🔄 Phase dbt"
  cd /app/dbt
  DBT_PROFILES_DIR=/app dbt run --select tag:staging --target $ENV || echo "⚠️ Staging skipped"
  DBT_PROFILES_DIR=/app dbt run --select tag:marts --target $ENV || echo "⚠️ Marts skipped"
  DBT_PROFILES_DIR=/app dbt test --select stg_* --target $ENV || echo "⚠️ Tests skipped"
  cd /app

  echo "✅ Batch terminé - Prochain run: $(date -d "+${INTERVAL_MIN} minutes")"
  sleep $((INTERVAL_MIN * 60))
done
