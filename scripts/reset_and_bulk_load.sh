#!/bin/bash
# Reset CDC + Bulk load Snowflake RAW
# Usage:
#   ./scripts/reset_and_bulk_load.sh          # Quick reset (purge CDC rows, keep bulk data)
#   ./scripts/reset_and_bulk_load.sh --full   # Full reload (truncate + bulk load 18 tables depuis MySQL)
set -euo pipefail

# 0. Charger .env
[ -f .env ] && { set -a; source .env; set +a; } && echo "✅ .env chargé"

CONNECTOR_NAME="${CONNECTOR_NAME:-winstat-rds}"
KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
CONSUMER_GROUP="medi_core_cdc_batch_dev2"
MODE="quick"

if [ "${1:-}" = "--full" ]; then
  MODE="full"
fi

echo "🔄 Reset MediCore CDC (mode: $MODE)"

# ============================================================
# Étape 1 : Stop CDC - Supprimer le connecteur Debezium
# ============================================================
echo "🛑 Étape 1 : Stop Debezium connector ($CONNECTOR_NAME)..."
curl -sf -X DELETE "http://localhost:8083/connectors/$CONNECTOR_NAME" && \
  echo "  ✅ Connector supprimé" || \
  echo "  ⚠️ Connector déjà absent"
sleep 3

# ============================================================
# Étape 2 : Purge données
# ============================================================
if [ "$MODE" = "quick" ]; then
  # Quick : supprimer uniquement les lignes CDC (garder les S = bulk load)
  echo "🗑️ Étape 2 : Purge lignes CDC des 4 tables transactionnelles..."
  snowsql -c medicore -q "
    DELETE FROM MEDICORE.RAW.RAW_COMMANDES WHERE cdc_operation != 'S';
    DELETE FROM MEDICORE.RAW.RAW_FACTURES  WHERE cdc_operation != 'S';
    DELETE FROM MEDICORE.RAW.RAW_ORDERS    WHERE cdc_operation != 'S';
    DELETE FROM MEDICORE.RAW.RAW_MODSTOCK  WHERE cdc_operation != 'S';
  "
  echo "  ✅ Lignes CDC purgées (données bulk S conservées)"
else
  # Full : truncate 18 tables + bulk load
  echo "🗑️ Étape 2 : Truncate 18 tables RAW..."
  snowsql -c medicore -q "
    TRUNCATE TABLE MEDICORE.RAW.RAW_COMMANDES;
    TRUNCATE TABLE MEDICORE.RAW.RAW_FACTURES;
    TRUNCATE TABLE MEDICORE.RAW.RAW_ORDERS;
    TRUNCATE TABLE MEDICORE.RAW.RAW_MODSTOCK;
    TRUNCATE TABLE MEDICORE.RAW.RAW_DAYBYDAY;
    TRUNCATE TABLE MEDICORE.RAW.RAW_EAN13;
    TRUNCATE TABLE MEDICORE.RAW.RAW_FOURNISSEURS;
    TRUNCATE TABLE MEDICORE.RAW.RAW_HISTORY;
    TRUNCATE TABLE MEDICORE.RAW.RAW_LOG;
    TRUNCATE TABLE MEDICORE.RAW.RAW_LPPR;
    TRUNCATE TABLE MEDICORE.RAW.RAW_MANQHISTORY;
    TRUNCATE TABLE MEDICORE.RAW.RAW_MEDIPRIX_FACTURES;
    TRUNCATE TABLE MEDICORE.RAW.RAW_PHARMACIE;
    TRUNCATE TABLE MEDICORE.RAW.RAW_PRODUITS;
    TRUNCATE TABLE MEDICORE.RAW.RAW_PRODUITS_NEGATIFS;
    TRUNCATE TABLE MEDICORE.RAW.RAW_STOCKHISTORY;
    TRUNCATE TABLE MEDICORE.RAW.RAW_PHARMACIES;
    TRUNCATE TABLE MEDICORE.RAW.RAW_PHARMACIES_ERREUR;
  "
  echo "  ✅ 18 tables truncated"

  # Étape 3 : Bulk load depuis MySQL RDS
  echo "📦 Étape 3 : Bulk load MySQL RDS → Snowflake RAW (18 tables)..."
  docker exec medicore_elt_batch python //app/pipelines/bulk_load.py
  echo "  ✅ Bulk load terminé"
fi

# ============================================================
# Reset Debezium : Recréer le connecteur (schema_only)
# ============================================================
if [ "$MODE" = "quick" ]; then
  STEP_NUM="3"
else
  STEP_NUM="4"
fi
echo "🔌 Étape $STEP_NUM : Recréer connecteur Debezium (schema_only)..."
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
  echo ""
  echo "  ✅ Connector recréé (schema_only)"
else
  echo ""
  echo "  ❌ Erreur création connector"
  exit 1
fi

# ============================================================
# Delete consumer group + Restart
# ============================================================
LAST_STEP=$((STEP_NUM + 1))
echo "🔄 Étape $LAST_STEP : Reset Kafka consumer group + restart..."
docker exec kafka kafka-consumer-groups --bootstrap-server kafka:9092 \
  --delete --group "$CONSUMER_GROUP" 2>/dev/null && \
  echo "  ✅ Consumer group $CONSUMER_GROUP supprimé" || \
  echo "  ⚠️ Consumer group déjà absent"

# Restart batch loop (container restart policy = unless-stopped)
docker restart medicore_elt_batch
echo "  ✅ medicore_elt_batch redémarré"

echo ""
echo "🎉 Reset terminé (mode: $MODE)"
echo "📊 Vérifier : docker logs medicore_elt_batch --tail 20"
echo "📊 Connector : curl -s http://localhost:8083/connectors/$CONNECTOR_NAME/status | jq ."
