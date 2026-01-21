#!/bin/bash

# Version Docker (curl Debezium)

echo "🏗️ Setup MediCore Pipeline"

# 1. Test connexions
echo "🔌 Test Snowflake..."
python -c "
from utils.snowflake_connector import SnowflakeConnector
SnowflakeConnector().conn.cursor().execute('SELECT 1')
print('✅ Snowflake OK')
"

# 2. Configurer Debezium connector
echo "🔌 Config Debezium..."
# curl -X POST http://localhost:8083/connectors \
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "winstat-connector",
    "config": {
      "connector.class": "io.debezium.connector.mysql.MySqlConnector",
      "database.hostname": "mysql_cdc",
      "database.port": "3306",
      "database.user": "cdc_user",
      "database.password": "cdc_password",
      "database.server.id": "184054",
      "database.include.list": "winstat",
      "table.include.list": "winstat.COMMANDES,winstat.FACTURES",
      "topic.prefix": "winstat"
    }
  }'

# 3. Création des objets Snowflake (Warehouse, rôles, tables...)
echo "🏗️ Création tables RAW Snowflake..."
docker exec medicore_elt_batch snowsql -f /app/sql/DDL_WH.sql
docker exec medicore_elt_batch snowsql -f /app/sql/DDL_TABLES.sql

echo "🚀 Setup terminé ! docker compose up -d"
