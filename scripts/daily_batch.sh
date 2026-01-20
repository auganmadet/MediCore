#!/bin/bash

# Si le pipeline est exécuté en dehors du container : docker exec medicore_elt_batch
# Ce script n'est pas utilisé actuellement mais gardé comme alternative si un jour 
# les runs depuis l’hôte

# Run quotidien 00h01 - traite les nouveautés du jour

echo "🕐 Batch quotidien MediCore - $(date)"

# 1. Pipeline CDC → Kafka → Snowflake RAW (nouveautés)
docker exec medicore_elt_batch python /app/pipelines/daily_cdc_batch.py

# 2. dbt incremental STAGING
docker exec medicore_elt_batch dbt run --select tag:staging --target $ENV

# 3. dbt MARTS
docker exec medicore_elt_batch dbt run --select tag:marts --target $ENV

# 4. Tests
docker exec medicore_elt_batch dbt test --select stg_* --target $ENV

echo "✅ Batch quotidien terminé !"
