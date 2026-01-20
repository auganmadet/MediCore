#!/bin/bash
# Version Docker du pipeline lancée manuellement
# Peut être supprimée car substitué par batch_loop.sh 
set -euo pipefail

ENV=${1:-dev}
cd /app

echo "🚀 MediCore Pipeline Docker - $ENV ($(date))"

# 1. dbt deps (cache docker)
dbt deps --target $ENV

# 2. RAW layer (views)
echo "📥 RAW layer (views - full refresh implicite)"
dbt run --select tag:raw --target $ENV

# 3. STAGING layer (tables nettoyées et incrémentales)
echo "🔄 STAGING layer (déduplication CDC et incremental)"
dbt run --select tag:staging --target $ENV

# 4. MARTS layer (dimensions + faits)
echo "📊 MARTS layer (business logic)"
dbt run --select tag:marts --target $ENV

# 5. Data quality
echo "✅ Data quality tests : sources + staging"
# dbt test --select sources+ --target $ENV
dbt test --select source:mysql_raw.* --target $ENV
dbt test --select stg_* --target $ENV

# 6. Freshness & docs
dbt source freshness check --select mysql_raw.* --target $ENV
dbt docs generate --target $ENV

echo "🎉 Pipeline MediCore terminé avec succès ! Consultez dbt docs: http://localhost:8080"
# echo "📊 Tables créées: RAW(views) → STAGING(tables) → MARTS(tables)"
