#!/bin/bash
set -euo pipefail

echo "🚀 MediCore Entrypoint - $(date) - ENV: $ENV"

# Env vars Snowflake
export SNOWFLAKE_ACCOUNT=${SNOWFLAKE_ACCOUNT:-}
export SNOWFLAKE_USER=${SNOWFLAKE_USER:-}
export SNOWFLAKE_PASSWORD=${SNOWFLAKE_PASSWORD:-}
export SNOWFLAKE_ROLE_NAME=${SNOWFLAKE_ROLE_NAME:-MEDIcore_DBT_EXECUTOR}
export SNOWFLAKE_DATABASE=${SNOWFLAKE_DATABASE:-MEDIcore}
export SNOWFLAKE_WAREHOUSE_NAME=${SNOWFLAKE_WAREHOUSE_NAME:-MEDIcore_WH}

echo "✅ SNOWFLAKE_ACCOUNT=${SNOWFLAKE_ACCOUNT:0:8}***"

# Attendre Kafka (bash /dev/tcp natif)
echo "⏳ Waiting for dependencies..."
until (echo > /dev/tcp/kafka/9092) >/dev/null 2>&1; do echo "⏳ kafka:9092..."; sleep 2; done
echo "✅ kafka:9092 ready"

# Attendre MySQL
until (echo > /dev/tcp/mysql_cdc/3306) >/dev/null 2>&1; do echo "⏳ mysql_cdc:3306..."; sleep 2; done
echo "✅ mysql_cdc:3306 ready"

# Launch batch
export DBT_PROFILES_DIR=/app
export BATCH_INTERVAL_MIN=${BATCH_INTERVAL_MIN:-5}
echo "🔄 Launching batch loop - ${BATCH_INTERVAL_MIN}min"
exec ./scripts/batch_loop.sh
