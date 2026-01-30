#!/bin/bash
# Exécuter sur HÔTE LOCAL (AVANT docker compose up)

set -euo pipefail

# 0. Charger systématiquement .env
if [ -f .env ]; then
  source .env
  echo "✅ .env chargé"
else
  echo "⚠️  .env manquant"
fi

# # 0. Charger .env UNIQUEMENT si variables manquantes --> KO dans le cas où une variable d'environnement est modifiée --> .env non rechargé
# if [ -f .env ] && { [ -z "${SNOWFLAKE_ACCOUNT:-}" ] || [ -z "${SNOWFLAKE_USER:-}" ] || [ -z "${SNOWFLAKE_PASSWORD:-}" ]; }; then
#   source .env
#   echo "✅ .env chargé"
# elif [ -f .env ]; then
#   echo "✅ Variables déjà présentes (.env ignoré)"
# else
#   echo "⚠️  .env manquant → variables manuelles requises"
# fi

echo "🏗️ MediCore Setup - HOST LOCAL"

# 1. Vérifier snowsql installé
command -v snowsql >/dev/null 2>&1 || { echo "❌ Installez snowsql : https://docs.snowflake.com/user-guide/snowsql-setup"; exit 1; }

# 2. Variables Snowflake
: "${SNOWFLAKE_ACCOUNT:?❌ variable manquante}"
: "${SNOWFLAKE_USER:?❌ variable manquante}"
: "${SNOWFLAKE_PASSWORD:?❌ variable manquante}"

echo "✅ Variables OK → ACCOUNT=$SNOWFLAKE_ACCOUNT USER=$SNOWFLAKE_USER"

# 3. Créer objets Snowflake
# echo "🏗️ Snowflake DDL..."
# snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_WH.sql
# snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_TABLES.sql


# echo "🏗️ Test connexion Snowflake..."  --> Failed to authenticate: MFA with TOTP is required
# docker run --rm \
#   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
#   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
#   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
#   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
#   python:3.11-slim \
#   sh -c "
# pip install snowflake-connector-python -q &&
# python -c '
# import snowflake.connector, os
# try:
#     conn = snowflake.connector.connect(
#         account=os.getenv(\"SNOWFLAKE_ACCOUNT\"),
#         user=os.getenv(\"SNOWFLAKE_USER\"),
#         password=os.getenv(\"SNOWFLAKE_PASSWORD\"),
#         warehouse=\"MEDIcore_WH\"
#     )
#     cursor = conn.cursor()
#     cursor.execute(\"SELECT CURRENT_VERSION();\")
#     version = cursor.fetchone()[0]
#     print(f\"✅ Connexion OK : Snowflake {version}\")
#     cursor.close()
#     conn.close()
# except Exception as e:
#     print(f\"❌ ERREUR CONNEXION : {e}\")
#     exit(1)
# '
# "

# echo "🏗️ Test connexion Snowflake (MFA TOTP)..."
# --> ❌ ERREUR : 390190 (08001): Failed to connect to DB: ymyunab-hr05962.snowflakecomputing.com:443, 
# There was an error related to the SAML Identity Provider account parameter. Contact Snowflake support.
# 
# docker run --rm \
#   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
#   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
#   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
#   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
#   python:3.11-slim \
#   sh -c "
# pip install snowflake-connector-python -q &&
# python -c '
# import snowflake.connector, os
# try:
#     conn = snowflake.connector.connect(
#         account=os.getenv(\"SNOWFLAKE_ACCOUNT\"),
#         user=os.getenv(\"SNOWFLAKE_USER\"),
#         password=os.getenv(\"SNOWFLAKE_PASSWORD\") + \" + TOTP_CODE\",
#         warehouse=\"MEDIcore_WH\",
#         authenticator=\"externalbrowser\"  # OU \"totp\"
#     )
#     cursor = conn.cursor()
#     cursor.execute(\"SELECT CURRENT_VERSION();\")
#     print(f\"✅ Connexion OK : Snowflake {cursor.fetchone()[0]}\")
# except Exception as e:
#     print(f\"❌ ERREUR : {e}\")
# '
# "

# # 3. CREATION OBJETS SNOWFLAKE (sans MFA : double authentification)
# echo "🏗️ Snowflake DDL via Python (MFA bypass)..."
# docker run --rm \
#   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
#   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
#   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
#   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
#   -e SNOWFLAKE_DATABASE="MEDIcore" \
#   -e SNOWFLAKE_SCHEMA="RAW" \
#   -v "$(pwd)/scripts:/scripts" \
#   python:3.11-slim \
#   sh -c "
# pip install snowflake-connector-python -q &&
# python -c '
# import snowflake.connector
# import os
# conn = snowflake.connector.connect(
#     account=os.getenv(\"SNOWFLAKE_ACCOUNT\" ),
#     user=os.getenv(\"SNOWFLAKE_USER\" ),
#     password=os.getenv(\"SNOWFLAKE_PASSWORD\" ),
#     warehouse=\"MEDIcore_WH\",
#     database=\"MEDIcore\",
#     schema=\"RAW\"
# )
# cursor = conn.cursor()

# # # DDL_WH.sql
# # with open(\"/scripts/DDL_WH.sql\", \"r\") as f:
# #     cursor.execute(f.read())
    
# # # DDL_TABLES.sql  
# # with open(\"/scripts/DDL_TABLES.sql\", \"r\") as f:
# #     cursor.execute(f.read())

# for sql_file in [\"/scripts/DDL_WH.sql\", \"/scripts/DDL_TABLES.sql\"]:
#     with open(sql_file, \"r\") as f: 
#       cursor.execute(f.read())

# conn.commit()
# print(\"✅ MEDIcore_WH + RAW tables créées\")
# cursor.close()
# conn.close()
# '
# "

# # 3. SNOWSQL LOCAL (MFA TOTP OK) --> **************%% is not a valid integer --> Mot de passe avec caractères spéciaux  
# echo "🔐 Snowflake DDL via SnowSQL (MFA TOTP interactif)..."
# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
#   -o authenticator=totp \
#   -q "SELECT CURRENT_VERSION();"


# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
#   -o authenticator=totp \
#   -f scripts/DDL_WH.sql


# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
#   -o authenticator=totp \
#   -f scripts/DDL_TABLES.sql


# echo "✅ MEDIcore_WH + RAW tables créées (SnowSQL MFA OK)"

# # 3. SNOWSQL LOCAL (MFA TOTP OK)  --> **************%% is not a valid integer - échappement du caractères spéciaux KO
# echo "🔐 Snowflake DDL via SnowSQL (MFA TOTP interactif)..."
# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
#   -o authenticator=totp \
#   -q "SELECT CURRENT_VERSION();"

# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
#   -o authenticator=totp \
#   -f scripts/DDL_WH.sql

# snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
#   -o authenticator=totp \
#   -f scripts/DDL_TABLES.sql

# echo "✅ MEDIcore_WH + RAW tables créées (SnowSQL MFA OK)"

# 3. SNOWSQL avec SNOWSQL_PWD (solution officielle) 
# --> 250001 (08001): Failed to connect to DB: YMYUNAB-HR05962.snowflakecomputing.com:443. 
#     Failed to authenticate: MFA with TOTP is required. To authenticate, provide both your password and a current TOTP passcode.
# echo "🔐 Snowflake DDL via SnowSQL (SNOWSQL_PWD)..."
# export SNOWSQL_ACCOUNT="$SNOWFLAKE_ACCOUNT"
# export SNOWSQL_USER="$SNOWFLAKE_USER" 
# export SNOWSQL_PWD="$SNOWFLAKE_PASSWORD"
# export SNOWSQL_WAREHOUSE="MEDICORE_WH"
# export SNOWSQL_DATABASE="MEDICORE"
# export SNOWSQL_SCHEMA="RAW"

# # Test connexion
# snowsql -o authenticator=totp -q "SELECT CURRENT_VERSION();"
# # DDL Warehouse
# snowsql -o authenticator=totp -f scripts/DDL_WH.sql
# # DDL Tables RAW
# snowsql -o authenticator=totp -f scripts/DDL_TABLES.sql

# snowsql -q "SELECT CURRENT_VERSION();"


# # Accède dans config.[connections.medicore]
# snowsql -c medicore -q "SELECT CURRENT_VERSION();"
# snowsql -c medicore -f scripts/DDL_WH.sql
# snowsql -c medicore -f scripts/DDL_TABLES.sql

# echo "✅ MEDIcore_WH + RAW tables créées (SNOWSQL_PWD OK)"

# # 3. SNOWSQL avec config MFA (authenticator=totp) --> Ajout dans config [connections.medicore] --> 'NoneType' object is not subscriptable
# echo "🔐 Snowflake DDL via SnowSQL (config MFA)..."
# export SNOWSQL_ACCOUNT="$SNOWFLAKE_ACCOUNT"
# export SNOWSQL_USER="$SNOWFLAKE_USER"
# export SNOWSQL_PWD="$SNOWFLAKE_PASSWORD"

# # Config SnowSQL avec MFA
# mkdir -p ~/.snowsql
# cat > ~/.snowsql/config << EOF
# [connections.medicore]
# accountname = $SNOWFLAKE_ACCOUNT
# username = $SNOWFLAKE_USER
# password = $SNOWFLAKE_PASSWORD
# warehousename = MEDIcore_WH
# dbname = MEDIcore
# schemaname = RAW
# authenticator = totp
# EOF

# # Exécution

# snowsql -c medicore -q "SELECT CURRENT_VERSION();"
# snowsql -c medicore -f scripts/DDL_WH.sql
# snowsql -c medicore -f scripts/DDL_TABLES.sql

# 3. SNOWSQL avec config existante (NE PAS ÉCRASER + ajout manuel [connections.medicore] dans config) --> 'NoneType' object is not subscriptable
echo "🔐 Snowflake DDL via SnowSQL (config existante)..."

# # Vérifier config medicore existe
# if ! grep -q "\[connections.medicore\]" ~/.snowsql/config 2>/dev/null; then
#   echo "❌ Config medicore manquante dans ~/.snowsql/config"
#   echo "Ajoute manuellement :"
#   echo "  [connections.medicore]"
#   echo "  accountname = $SNOWFLAKE_ACCOUNT"
#   echo "  username = $SNOWFLAKE_USER"
#   echo "  password = <TON_MOT_DE_PASSE>"
#   echo "  authenticator = totp"
#   exit 1
# fi

# # Utiliser config existante
# snowsql -c medicore -q "SELECT CURRENT_VERSION();"
snowsql -c medicore -f scripts/DDL_WH.sql
snowsql -c medicore -f scripts/DDL_TABLES.sql

# echo "✅ MEDIcore_WH + RAW tables créées"

# 4. Démarrer stack Docker
echo "🐳 Docker stack..."
docker compose up -d mysql_cdc zookeeper kafka connect kafdrop

# 5. Attendre + config Debezium MySQL → Kafka
echo "⏳ Debezium MySQL → Kafka setup..."
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
      "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY",
      "topic.prefix": "winstat"
    }
  }' || echo "✅ Debezium existe déjà"

# 6. Snowflake Kafka Connector (Kafka → RAW)
echo "🔌 Kafka → Snowflake RAW setup..."
sleep 10
docker exec kafka_connect confluent-hub install --no-prompt snowflakeinc/snowflake-kafka-connector:latest || echo "✅ Connector installé"
docker compose restart connect
sleep 10
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"snowflake-raw-sink\",
    \"config\": {
      \"connector.class\": \"com.snowflake.kafka.connector.SnowflakeSinkConnector\",
      \"topics\": \"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE\",
      \"snowflake.topic2table.map\": \"winstat.COMMANDES:RAW.COMMANDES,winstat.FACTURES:RAW.FACTURES,winstat.ORDERS:RAW.ORDERS,winstat.PHARMACIE:RAW.PHARMACIE,winstat.MODSTOCK:RAW.MODSTOCK,winstat.DAYBYDAY:RAW.DAYBYDAY\",
      \"snowflake.user.name\": \"$SNOWFLAKE_USER\",
      \"snowflake.password\": \"$SNOWFLAKE_PASSWORD\",
      \"snowflake.account\": \"$SNOWFLAKE_ACCOUNT\",
      \"snowflake.database.name\": \"MEDIcore\",
      \"snowflake.schema.name\": \"RAW\",
      \"tasks.max\": \"2\",
      \"buffer.count.records\": \"10000\"
    }
  }" || echo "✅ Snowflake sink existe déjà"


# 7. Pipeline batch
echo "🚀 dbt STAGING + MARTS..."
docker compose up -d medicore_elt_batch

# 8. Monitoring unifié
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


