#!/bin/bash
set -euo pipefail

# 0. Charger systématiquement .env
[ -f .env ] && { set -a; source .env; set +a; } && echo "✅ .env chargé"
echo "🏗️ MediCore Setup - HOST LOCAL"
echo "🔍 VARS: CONNECTOR_NAME=$CONNECTOR_NAME MYSQL_HOST=$MYSQL_HOST"

# 1. Vérifier snowsql, docker, docker-compose installés
command -v snowsql >/dev/null 2>&1 || { echo "❌ Installez snowsql : https://docs.snowflake.com/user-guide/snowsql-setup"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Installez Docker"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ Installez docker-compose"; exit 1; }
command -v jq >/dev/null 2>&1 || { 
  echo "❌ jq manquant. Dans Git Bash :"
  echo "  mkdir -p ~/bin && curl -L -o ~/bin/jq.exe https://github.com/jqlang/jq/releases/latest/download/jq-win64.exe"
  echo "  echo 'export PATH=\"\$HOME/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
  exit 1
}
# 2. Clean total + démarrage progressif
echo "🧹 Clean + Stack progressive..."
docker compose down -v --remove-orphans 2>/dev/null || true
docker system prune -f 2>/dev/null || true

# 3. Variables Snowflake
: "${SNOWFLAKE_ACCOUNT:?❌ variable manquante}"
: "${SNOWFLAKE_USER:?❌ variable manquante}"
: "${SNOWFLAKE_PASSWORD:?❌ variable manquante}"

echo "✅ Variables OK → ACCOUNT=$SNOWFLAKE_ACCOUNT USER=$SNOWFLAKE_USER"

# 3. SNOWSQL avec config existante (NE PAS ÉCRASER + ajout manuel [connections.medicore] dans config) --> 'NoneType' object is not subscriptable
# Vérifier config medicore existe
if ! grep -q "\[connections.medicore\]" ~/.snowsql/config 2>/dev/null; then
  echo "❌ Config medicore manquante dans ~/.snowsql/config"
  echo "Ajoute manuellement :"
  echo "  [connections.medicore]"
  echo "  accountname = $SNOWFLAKE_ACCOUNT"
  echo "  username = $SNOWFLAKE_USER"
  echo "  authenticator = snowflake"
  echo "  password = $SNOWFLAKE_PASSWORD"
  echo "  warehousename = $SNOWFLAKE_WAREHOUSE_NAME"
  echo "  database = $SNOWFLAKE_DATABASE"
  echo "  schemaname = $SNOWFLAKE_SCHEMA_NAME"
  echo "  rolename = $SNOWFLAKE_ROLE_NAME"
  exit 1
fi

RUN_SNOWFLAKE_DDL="${RUN_SNOWFLAKE_DDL:-false}"
if [ "${1-}" = "--with-snowflake-ddl" ]; then
  RUN_SNOWFLAKE_DDL=true
fi

if [ "$RUN_SNOWFLAKE_DDL" = "true" ]; then
  echo "🔐 Snowflake DDL via SnowSQL (config existante)..."
  # Utiliser config existante
  snowsql -c medicore -f scripts/DDL_WH.sql
  snowsql -c medicore -f scripts/DDL_TABLES.sql
  echo "✅ Tables RAW créées"
else
  echo "⏭️ Skip Snowflake DDL (RUN_SNOWFLAKE_DDL != true)."
fi

# 4. Démarrer stack Docker
echo "🐳 Docker stack..."

# Phase 1 : mysql_cdc zookeeper kafka kafdrop (45s max)
echo "🐳 Phase 1/4 : mysql_cdc zookeeper kafka kafdrop"
docker compose up -d mysql_cdc zookeeper kafka kafdrop
echo "⏳ Attente Kafka healthy (45s)..."
sleep 45

# Phase 2 : Connect
echo "🔌 Phase 2/4 : connect"
docker compose up -d connect 
sleep 25

# Phase 3 : Debezium connector
echo "📦 Phase 3/4 : Debezium → RDS Winstat..."

# Attendre API
echo "⏳ Connect API..."
ready=false
for i in {1..180}; do
  if curl -s http://localhost:8083/ | jq -e '.version' >/dev/null 2>&1; then
    echo "✅ Connect API prête ! ($i s)"
    ready=true
    break
  fi
  sleep 1
done

if [ "$ready" != "true" ]; then
  echo "❌ Connect API non disponible après 180s"
  exit 1
fi

# Pré-créer schema_history
docker exec kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic winstat_schema_history --partitions 1 --replication-factor 1 || true

CONNECTOR_NAME="${CONNECTOR_NAME:-winstat-rds}"  # ← FIX sécurité

# Phase 3b : Build + start ELT batch (avant bulk load et avant Debezium)
echo "🚀 Phase 3b/4 : medicore-elt-batch (build)..."
docker compose build --no-cache medicore-elt-batch
docker compose up -d medicore-elt-batch
echo "⏳ Attente container medicore_elt_batch (15s)..."
sleep 15

# Phase 3c : Bulk load initial MySQL → Snowflake RAW
echo "📦 Phase 3c/4 : Bulk load initial (18 tables)..."
docker exec medicore_elt_batch python //app/pipelines/bulk_load.py --truncate

# "snapshot.mode": "schema_only"
if curl -f -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "'$CONNECTOR_NAME'",
    "config": {
      "connector.class": "io.debezium.connector.mysql.MySqlConnector",
      "database.hostname": "'"$MYSQL_HOST"'",
      "database.port": "'"$MYSQL_PORT"'",
      "database.user": "'"$MYSQL_USER"'",
      "database.password": "'"$MYSQL_PASSWORD"'",
      "database.server.id": "184054",
      "database.include.list": "winstat",
      "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
      "topic.prefix": "winstat_rds",
      "snapshot.mode": "schema_only",
      "snapshot.locking.mode": "minimal",
      "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
      "schema.history.internal.kafka.topic": "winstat_schema_history",
      "schema.history.internal.store.only.captured.tables.ddl": "true",
      "tasks.max": "1"
    }
  }'; then
  echo "✅ CDC STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
else
  echo "❌ ERREUR connector"
  exit 1
fi

echo "⏳ Attente CDC RUNNING (45s)..."
sleep 45

echo "🎉 PIPELINE 100% OPÉRATIONNEL !"
echo "📊 Logs     : docker logs -f medicore_elt_batch"
echo "🔍 Kafka UI : http://localhost:9000" 
echo "🔍 Connect  : curl http://localhost:8083/connectors"

# Status final
echo "📈 STATUS :"
# curl -s http://localhost:8083/connectors | jq '.[].name' 2>/dev/null || echo "Connecteurs pas démarrés"
# docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(kafka|mysql|connect|kafdrop|medicore|zookeeper)"  

echo "Connector: $(curl -s http://localhost:8083/connectors/$CONNECTOR_NAME/status 2>/dev/null | jq -r '.tasks[0].state // "DÉMARRAGE"')"
echo "Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(kafka|connect|elt)"
echo ""
echo "📊 MONITORING (2 terminaux):"
echo "T1: while true; do clear; curl -s http://localhost:8083/connectors/$CONNECTOR_NAME/status | jq .; sleep 3; done"
echo "T2: docker logs -f kafka_connect 2>&1 | grep -E '(winstat|binlog|Producer)'"