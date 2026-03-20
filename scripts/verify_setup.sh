#!/bin/bash
# verify_setup.sh - Vérifie que le pipeline MediCore est opérationnel
# Usage: ./scripts/verify_setup.sh
set -euo pipefail

# Charger .env
[ -f .env ] && { set -a; source .env; set +a; }

CONNECTOR_NAME="${CONNECTOR_NAME:-winstat-rds}"

echo "=== VÉRIFICATION PIPELINE MEDICORE ==="
echo ""

ERRORS=0

# 1. Docker services
echo "🐳 1/5 Docker services..."
SERVICES=("mysql_cdc" "zookeeper" "kafka" "connect" "kafdrop" "medicore-elt-batch")
for svc in "${SERVICES[@]}"; do
  STATUS=$(docker compose ps --format json 2>/dev/null | jq -r "select(.Service == \"$svc\") | .State" 2>/dev/null || echo "absent")
  if [ "$STATUS" = "running" ]; then
    echo "   ✅ $svc: running"
  else
    echo "   ❌ $svc: $STATUS"
    ERRORS=$((ERRORS + 1))
  fi
done
echo ""

# 2. Debezium connector
echo "🔌 2/5 Debezium connector..."
CONNECTOR_STATUS=$(curl -s "http://localhost:8083/connectors/$CONNECTOR_NAME/status" 2>/dev/null | jq -r '.tasks[0].state // "ABSENT"')
if [ "$CONNECTOR_STATUS" = "RUNNING" ]; then
  echo "   ✅ Connector $CONNECTOR_NAME: RUNNING"
else
  echo "   ❌ Connector $CONNECTOR_NAME: $CONNECTOR_STATUS"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# 3. Kafka topics CDC
echo "📨 3/5 Kafka topics..."
TOPICS=$(docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list 2>/dev/null | grep -c "winstat_rds" || echo "0")
if [ "$TOPICS" -ge 4 ]; then
  echo "   ✅ $TOPICS topics CDC trouvés (winstat_rds.*)"
else
  echo "   ❌ Seulement $TOPICS topics CDC (attendu: 4+)"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# 4. Snowflake RAW tables
echo "❄️  4/5 Snowflake RAW (via snowsql -c medicore)..."
if command -v snowsql >/dev/null 2>&1; then
  # Vérifier nombre de tables RAW
  TABLE_COUNT=$(snowsql -c medicore -q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'RAW';" -o output_format=plain -o header=false 2>/dev/null | tr -d ' \n' || echo "0")
  if [ "$TABLE_COUNT" -ge 18 ]; then
    echo "   ✅ $TABLE_COUNT tables RAW trouvées"
  else
    echo "   ❌ Seulement $TABLE_COUNT tables RAW (attendu: 18)"
    ERRORS=$((ERRORS + 1))
  fi
  
  # Vérifier données dans RAW_COMMANDES (table CDC principale)
  ROW_COUNT=$(snowsql -c medicore -q "SELECT COUNT(*) FROM MEDICORE_PROD.RAW.RAW_COMMANDES;" -o output_format=plain -o header=false 2>/dev/null | tr -d ' \n' || echo "0")
  if [ "$ROW_COUNT" -gt 0 ]; then
    echo "   ✅ RAW_COMMANDES: $ROW_COUNT lignes"
  else
    echo "   ⚠️  RAW_COMMANDES: vide (bulk load en attente ?)"
  fi
else
  echo "   ⚠️  snowsql non installé - skip vérification Snowflake"
fi
echo ""

# 5. dbt connectivity (via container)
echo "📊 5/5 dbt connectivity..."
if docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt debug --target dev" >/dev/null 2>&1; then
  echo "   ✅ dbt peut se connecter à Snowflake"
else
  echo "   ❌ dbt debug failed"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# Résumé
echo "============================================"
if [ "$ERRORS" -eq 0 ]; then
  echo "🎉 PIPELINE 100% OPÉRATIONNEL !"
  echo ""
  echo "Prochaines étapes :"
  echo "  - Logs CDC      : docker logs -f medicore_elt_batch"
  echo "  - Kafka UI      : http://localhost:9000"
  echo "  - Connector     : curl http://localhost:8083/connectors/$CONNECTOR_NAME/status | jq ."
  exit 0
else
  echo "❌ $ERRORS ERREUR(S) DÉTECTÉE(S)"
  echo ""
  echo "Actions correctives :"
  echo "  - Relancer setup : ./scripts/setup.sh --with-snowflake-ddl"
  echo "  - Logs Docker    : docker compose logs -f"
  echo "  - Logs Connect   : docker logs kafka_connect --tail 50"
  exit 1
fi
