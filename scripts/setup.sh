#!/bin/bash
# Exécuter sur HÔTE LOCAL (AVANT docker compose up)

set -euo pipefail

echo "🏗️ MediCore Setup - HOST LOCAL"

# 1. Vérifier snowsql installé
command -v snowsql >/dev/null 2>&1 || { echo "❌ Installez snowsql : https://docs.snowflake.com/user-guide/snowsql-setup"; exit 1; }

# 2. Variables Snowflake
: "${SNOWFLAKE_ACCOUNT:?Manquant}"
: "${SNOWFLAKE_USER:?Manquant}"
: "${SNOWFLAKE_PASSWORD:?Manquant}"

# 3. Créer objets Snowflake
# echo "🏗️ Snowflake DDL..."
# snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_WH.sql
# snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_TABLES.sql

# 3. CREATION OBJETS SNOWFLAKE (sans MFA : double authentification)
echo "🏗️ Snowflake DDL via Python (MFA bypass)..."
docker run --rm \
  -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
  -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
  -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
  -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
  -e SNOWFLAKE_DATABASE="MEDIcore" \
  -e SNOWFLAKE_SCHEMA="RAW" \
  -v "$(pwd)/scripts:/scripts" \
  python:3.11-slim \
  sh -c "
pip install snowflake-connector-python -q &&
python -c '
import snowflake.connector
import os
conn = snowflake.connector.connect(
    account=os.getenv(\"SNOWFLAKE_ACCOUNT\" ),
    user=os.getenv(\"SNOWFLAKE_USER\" ),
    password=os.getenv(\"SNOWFLAKE_PASSWORD\" ),
    warehouse=\"MEDIcore_WH\",
    database=\"MEDIcore\",
    schema=\"RAW\"
)
cursor = conn.cursor()

# DDL_WH.sql
with open(\"/scripts/DDL_WH.sql\", \"r\") as f:
    cursor.execute(f.read())
    
# DDL_TABLES.sql  
with open(\"/scripts/DDL_TABLES.sql\", \"r\") as f:
    cursor.execute(f.read())

conn.commit()
print(\"✅ MEDIcore_WH + RAW tables créées\")
cursor.close()
conn.close()
'
"

# 4. Démarrer stack Docker
echo "🐳 Docker stack..."
docker compose up -d mysql_cdc zookeeper kafka connect kafdrop

# 5. Attendre + config Debezium
echo "⏳ Debezium setup..."
sleep 30
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "winstat-medicore",
    "config": {
      "connector.class": "io.debezium.connector.mysql.MySqlConnector",
      "database.hostname": "localhost",
      "database.port": "3307",
      "database.user": "cdc_user",
      "database.password": "cdc_password",
      "database.server.id": "184054",
      "database.include.list": "winstat",
      "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE",
      "topic.prefix": "winstat"
    }
  }'

# 6. Pipeline batch
docker compose up -d medicore_elt_batch

# 7. Monitoring unifié
echo "🎉 100% opérationnel !"
echo "📊 Logs : docker logs -f medicore_elt_batch"
echo "🔍 Kafka : http://localhost:9000"
echo "🔍 Debezium : curl http://localhost:8083/connectors"
echo "🔍 Snowflake RAW : snowsql -q \"USE MEDIcore.RAW; SELECT COUNT(*) FROM RAW_COMMANDES\""

# Monitoring rapide
echo "📈 STATUS ACTUEL :"
docker logs medicore_elt_batch --tail 10
curl -s http://localhost:8083/connectors | jq '.[].name'
# docker logs medicore_elt_batch --tail 5 2>/dev/null || echo "Pipeline démarre..."
# curl -s http://localhost:8083/connectors 2>/dev/null | jq '.[].name' || echo "Debezium OK"