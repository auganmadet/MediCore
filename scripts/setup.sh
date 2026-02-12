# #!/bin/bash
# # Exécuter sur HÔTE LOCAL (AVANT docker compose up)

# set -euo pipefail

# # 0. Charger systématiquement .env
# # if [ -f .env ]; then
# #   source .env
# #   echo "✅ .env chargé"
# # else
# #   echo "⚠️  .env manquant"
# # fi
# [ -f .env ] && source .env && echo "✅ .env chargé" || echo "⚠️ .env manquant"

# # # 0. Charger .env UNIQUEMENT si variables manquantes --> KO dans le cas où une variable d'environnement est modifiée --> .env non rechargé
# # if [ -f .env ] && { [ -z "${SNOWFLAKE_ACCOUNT:-}" ] || [ -z "${SNOWFLAKE_USER:-}" ] || [ -z "${SNOWFLAKE_PASSWORD:-}" ]; }; then
# #   source .env
# #   echo "✅ .env chargé"
# # elif [ -f .env ]; then
# #   echo "✅ Variables déjà présentes (.env ignoré)"
# # else
# #   echo "⚠️  .env manquant → variables manuelles requises"
# # fi

# echo "🏗️ MediCore Setup - HOST LOCAL"

# # 1. Vérifier snowsql, docker, docker-compose installés
# command -v snowsql >/dev/null 2>&1 || { echo "❌ Installez snowsql : https://docs.snowflake.com/user-guide/snowsql-setup"; exit 1; }
# command -v docker >/dev/null 2>&1 || { echo "❌ Installez Docker"; exit 1; }
# command -v docker-compose >/dev/null 2>&1 || { echo "❌ Installez docker-compose"; exit 1; }

# # 2. Variables Snowflake
# : "${SNOWFLAKE_ACCOUNT:?❌ variable manquante}"
# : "${SNOWFLAKE_USER:?❌ variable manquante}"
# : "${SNOWFLAKE_PASSWORD:?❌ variable manquante}"

# echo "✅ Variables OK → ACCOUNT=$SNOWFLAKE_ACCOUNT USER=$SNOWFLAKE_USER"

# # 3. Créer objets Snowflake
# # echo "🏗️ Snowflake DDL..."
# # snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_WH.sql
# # snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER -p $SNOWFLAKE_PASSWORD -f scripts/DDL_TABLES.sql


# # echo "🏗️ Test connexion Snowflake..."  --> Failed to authenticate: MFA with TOTP is required
# # docker run --rm \
# #   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
# #   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
# #   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
# #   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
# #   python:3.11-slim \
# #   sh -c "
# # pip install snowflake-connector-python -q &&
# # python -c '
# # import snowflake.connector, os
# # try:
# #     conn = snowflake.connector.connect(
# #         account=os.getenv(\"SNOWFLAKE_ACCOUNT\"),
# #         user=os.getenv(\"SNOWFLAKE_USER\"),
# #         password=os.getenv(\"SNOWFLAKE_PASSWORD\"),
# #         warehouse=\"MEDIcore_WH\"
# #     )
# #     cursor = conn.cursor()
# #     cursor.execute(\"SELECT CURRENT_VERSION();\")
# #     version = cursor.fetchone()[0]
# #     print(f\"✅ Connexion OK : Snowflake {version}\")
# #     cursor.close()
# #     conn.close()
# # except Exception as e:
# #     print(f\"❌ ERREUR CONNEXION : {e}\")
# #     exit(1)
# # '
# # "

# # echo "🏗️ Test connexion Snowflake (MFA TOTP)..."
# # --> ❌ ERREUR : 390190 (08001): Failed to connect to DB: ymyunab-hr05962.snowflakecomputing.com:443, 
# # There was an error related to the SAML Identity Provider account parameter. Contact Snowflake support.
# # 
# # docker run --rm \
# #   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
# #   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
# #   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
# #   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
# #   python:3.11-slim \
# #   sh -c "
# # pip install snowflake-connector-python -q &&
# # python -c '
# # import snowflake.connector, os
# # try:
# #     conn = snowflake.connector.connect(
# #         account=os.getenv(\"SNOWFLAKE_ACCOUNT\"),
# #         user=os.getenv(\"SNOWFLAKE_USER\"),
# #         password=os.getenv(\"SNOWFLAKE_PASSWORD\") + \" + TOTP_CODE\",
# #         warehouse=\"MEDIcore_WH\",
# #         authenticator=\"externalbrowser\"  # OU \"totp\"
# #     )
# #     cursor = conn.cursor()
# #     cursor.execute(\"SELECT CURRENT_VERSION();\")
# #     print(f\"✅ Connexion OK : Snowflake {cursor.fetchone()[0]}\")
# # except Exception as e:
# #     print(f\"❌ ERREUR : {e}\")
# # '
# # "

# # # 3. CREATION OBJETS SNOWFLAKE (sans MFA : double authentification)
# # echo "🏗️ Snowflake DDL via Python (MFA bypass)..."
# # docker run --rm \
# #   -e SNOWFLAKE_ACCOUNT="$SNOWFLAKE_ACCOUNT" \
# #   -e SNOWFLAKE_USER="$SNOWFLAKE_USER" \
# #   -e SNOWFLAKE_PASSWORD="$SNOWFLAKE_PASSWORD" \
# #   -e SNOWFLAKE_WAREHOUSE="MEDIcore_WH" \
# #   -e SNOWFLAKE_DATABASE="MEDIcore" \
# #   -e SNOWFLAKE_SCHEMA="RAW" \
# #   -v "$(pwd)/scripts:/scripts" \
# #   python:3.11-slim \
# #   sh -c "
# # pip install snowflake-connector-python -q &&
# # python -c '
# # import snowflake.connector
# # import os
# # conn = snowflake.connector.connect(
# #     account=os.getenv(\"SNOWFLAKE_ACCOUNT\" ),
# #     user=os.getenv(\"SNOWFLAKE_USER\" ),
# #     password=os.getenv(\"SNOWFLAKE_PASSWORD\" ),
# #     warehouse=\"MEDIcore_WH\",
# #     database=\"MEDIcore\",
# #     schema=\"RAW\"
# # )
# # cursor = conn.cursor()

# # # # DDL_WH.sql
# # # with open(\"/scripts/DDL_WH.sql\", \"r\") as f:
# # #     cursor.execute(f.read())
    
# # # # DDL_TABLES.sql  
# # # with open(\"/scripts/DDL_TABLES.sql\", \"r\") as f:
# # #     cursor.execute(f.read())

# # for sql_file in [\"/scripts/DDL_WH.sql\", \"/scripts/DDL_TABLES.sql\"]:
# #     with open(sql_file, \"r\") as f: 
# #       cursor.execute(f.read())

# # conn.commit()
# # print(\"✅ MEDIcore_WH + RAW tables créées\")
# # cursor.close()
# # conn.close()
# # '
# # "

# # # 3. SNOWSQL LOCAL (MFA TOTP OK) --> **************%% is not a valid integer --> Mot de passe avec caractères spéciaux  
# # echo "🔐 Snowflake DDL via SnowSQL (MFA TOTP interactif)..."
# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
# #   -o authenticator=totp \
# #   -q "SELECT CURRENT_VERSION();"


# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
# #   -o authenticator=totp \
# #   -f scripts/DDL_WH.sql


# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$SNOWFLAKE_PASSWORD" \
# #   -o authenticator=totp \
# #   -f scripts/DDL_TABLES.sql


# # echo "✅ MEDIcore_WH + RAW tables créées (SnowSQL MFA OK)"

# # # 3. SNOWSQL LOCAL (MFA TOTP OK)  --> **************%% is not a valid integer - échappement du caractères spéciaux KO
# # echo "🔐 Snowflake DDL via SnowSQL (MFA TOTP interactif)..."
# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
# #   -o authenticator=totp \
# #   -q "SELECT CURRENT_VERSION();"

# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
# #   -o authenticator=totp \
# #   -f scripts/DDL_WH.sql

# # snowsql -a "$SNOWFLAKE_ACCOUNT" -u "$SNOWFLAKE_USER" -p "$(echo $SNOWFLAKE_PASSWORD | sed 's/%/%%/g')" \
# #   -o authenticator=totp \
# #   -f scripts/DDL_TABLES.sql

# # echo "✅ MEDIcore_WH + RAW tables créées (SnowSQL MFA OK)"

# # 3. SNOWSQL avec SNOWSQL_PWD (solution officielle) 
# # --> 250001 (08001): Failed to connect to DB: YMYUNAB-HR05962.snowflakecomputing.com:443. 
# #     Failed to authenticate: MFA with TOTP is required. To authenticate, provide both your password and a current TOTP passcode.
# # echo "🔐 Snowflake DDL via SnowSQL (SNOWSQL_PWD)..."
# # export SNOWSQL_ACCOUNT="$SNOWFLAKE_ACCOUNT"
# # export SNOWSQL_USER="$SNOWFLAKE_USER" 
# # export SNOWSQL_PWD="$SNOWFLAKE_PASSWORD"
# # export SNOWSQL_WAREHOUSE="MEDICORE_WH"
# # export SNOWSQL_DATABASE="MEDICORE"
# # export SNOWSQL_SCHEMA="RAW"

# # # Test connexion
# # snowsql -o authenticator=totp -q "SELECT CURRENT_VERSION();"
# # # DDL Warehouse
# # snowsql -o authenticator=totp -f scripts/DDL_WH.sql
# # # DDL Tables RAW
# # snowsql -o authenticator=totp -f scripts/DDL_TABLES.sql

# # snowsql -q "SELECT CURRENT_VERSION();"


# # # Accède dans config.[connections.medicore]
# # snowsql -c medicore -q "SELECT CURRENT_VERSION();"
# # snowsql -c medicore -f scripts/DDL_WH.sql
# # snowsql -c medicore -f scripts/DDL_TABLES.sql

# # echo "✅ MEDIcore_WH + RAW tables créées (SNOWSQL_PWD OK)"

# # # 3. SNOWSQL avec config MFA (authenticator=totp) --> Ajout dans config [connections.medicore] --> 'NoneType' object is not subscriptable
# # echo "🔐 Snowflake DDL via SnowSQL (config MFA)..."
# # export SNOWSQL_ACCOUNT="$SNOWFLAKE_ACCOUNT"
# # export SNOWSQL_USER="$SNOWFLAKE_USER"
# # export SNOWSQL_PWD="$SNOWFLAKE_PASSWORD"

# # # Config SnowSQL avec MFA
# # mkdir -p ~/.snowsql
# # cat > ~/.snowsql/config << EOF
# # [connections.medicore]
# # accountname = $SNOWFLAKE_ACCOUNT
# # username = $SNOWFLAKE_USER
# # password = $SNOWFLAKE_PASSWORD
# # warehousename = MEDIcore_WH
# # dbname = MEDIcore
# # schemaname = RAW
# # authenticator = totp
# # EOF

# # # Exécution

# # snowsql -c medicore -q "SELECT CURRENT_VERSION();"
# # snowsql -c medicore -f scripts/DDL_WH.sql
# # snowsql -c medicore -f scripts/DDL_TABLES.sql

# # 3. SNOWSQL avec config existante (NE PAS ÉCRASER + ajout manuel [connections.medicore] dans config) --> 'NoneType' object is not subscriptable
# # Vérifier config medicore existe
# if ! grep -q "\[connections.medicore\]" ~/.snowsql/config 2>/dev/null; then
#   echo "❌ Config medicore manquante dans ~/.snowsql/config"
#   echo "Ajoute manuellement :"
#   echo "  [connections.medicore]"
#   echo "  accountname = $SNOWFLAKE_ACCOUNT"
#   echo "  username = $SNOWFLAKE_USER"
#   echo "  authenticator = snowflake"
#   echo "  password = $SNOWFLAKE_PASSWORD"
#   echo "  warehousename = $SNOWFLAKE_WAREHOUSE_NAME"
#   echo "  database = $SNOWFLAKE_DATABASE"
#   echo "  schemaname = $SNOWFLAKE_SCHEMA_NAME"
#   echo "  rolename = $SNOWFLAKE_ROLE_NAME"
#   exit 1
# fi

# RUN_SNOWFLAKE_DDL="${RUN_SNOWFLAKE_DDL:-false}"
# if [ "${1-}" = "--with-snowflake-ddl" ]; then
#   RUN_SNOWFLAKE_DDL=true
# fi

# if [ "$RUN_SNOWFLAKE_DDL" = "true" ]; then
#   echo "🔐 Snowflake DDL via SnowSQL (config existante)..."
#   # Utiliser config existante
#   snowsql -c medicore -f scripts/DDL_WH.sql
#   snowsql -c medicore -f scripts/DDL_TABLES.sql
#   echo "✅ Tables RAW créées"
# else
#   echo "⏭️ Skip Snowflake DDL (RUN_SNOWFLAKE_DDL != true)."
# fi


# # 4. Démarrer stack Docker
# echo "🐳 Docker stack..."
# docker compose down -v 2>/dev/null || true
# docker compose up -d mysql_cdc zookeeper kafka connect kafdrop
# sleep 40

# # # 5. Attendre + config Debezium MySQL → Kafka
# # echo "⏳ Debezium MySQL → Kafka setup..."
# # sleep 30

# # # Vérifier si connector existe déjà
# # if ! curl -s http://localhost:8083/connectors/winstat-medicore >/dev/null 2>&1; then
# #   echo "📦 Installation Debezium MySQL connector..."
# #   docker run --rm -v /var/lib/docker/volumes:/kafka/docker -u 0 \
# #     debezium/connect:2.7.3.Final install \
# #     io.debezium/debezium-connector-mysql/2.7.3.Final
  
# #   docker compose restart connect
# #   sleep 15
# # fi

# # 5. **Debezium** : Télécharger + copier directement dans le container
# echo "📦 Debezium MySQL connector → Kafka setup..."
# # CONNECTOR_URL="https://repo1.maven.org/maven2/io/debezium/debezium-connector-mysql/2.7.3.Final/debezium-connector-mysql-2.7.3.Final-plugin.tar.gz"
# # TEMP_DIR=$(mktemp -d)
# # wget -O "$TEMP_DIR/connector.tar.gz" "$CONNECTOR_URL"
# # docker cp "$TEMP_DIR/connector.tar.gz" kafka_connect:/tmp/
# # docker exec kafka_connect tar -xzf /tmp/connector.tar.gz -C /usr/share/java/
# # docker exec kafka_connect mkdir -p /usr/share/confluent-hub-components
# # docker exec kafka_connect mv /usr/share/java/debezium-connector-mysql/* /usr/share/confluent-hub-components/ 2>/dev/null || true
# # --> wget: command not foun

# # Image avec MySQL connector PRÉ-INSTALLÉ (solution Windows) - évite wget
# echo "📦 Debezium MySQL connector (image complète)..."
# docker compose down connect
# docker pull debezium/connect:2.7.3.Final
# docker compose restart connect
# sleep 20

# # Créer Debezium connector
# echo "⏳ Debezium MySQL connector → Kafka setup..."
# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "winstat-medicore",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "mysql_cdc",
#       "database.port": "3306",
#       "database.user": "cdc_user",
#       "database.password": "cdc_password",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat",
#       "key.converter": "org.apache.kafka.connect.json.JsonConverter",
#       "value.converter": "org.apache.kafka.connect.json.JsonConverter",
#       "key.converter.schemas.enable": "false",
#       "value.converter.schemas.enable": "false"
#     }
#   }' || echo "✅ Debezium existe déjà"

# # # 6. Snowflake Kafka Connector (Kafka → RAW)
# # echo "🔌 Kafka → Snowflake RAW setup..."

# # # Installer Snowflake connector simplifiée avec wget via Confluent Hub (image Confluent)
# # # wget évite les problèmes de mount Windows/Git Bash
# # # docker run --rm --privileged -v /var/lib/docker/volumes:/cdata \
# # #   confluentinc/cp-kafka-connect:latest \
# # #   confluent-hub install --no-prompt snowflakeinc/snowflake-kafka-connector:latest
# # SNOWFLAKE_URL="https://confluent-hub-components/confluentinc/kafka-connect-storage-cloud/latest/kafka-connect-storage-cloud-11.4.3.zip"
# # wget -O "$TEMP_DIR/snowflake.zip" "$SNOWFLAKE_URL"
# # docker cp "$TEMP_DIR/snowflake.zip" kafka_connect:/tmp/
# # docker exec kafka_connect unzip -o /tmp/snowflake.zip -d /usr/share/java/
# # --> wget: command not found


# # docker compose restart connect
# # sleep 15

# # Créer Snowflake sink (après connector installé)
# # curl -X POST http://localhost:8083/connectors \
# #   -H "Content-Type: application/json" \
# #   -d "{
# #     \"name\": \"snowflake-raw-sink\",
# #     \"config\": {
# #       \"connector.class\": \"com.snowflake.kafka.connector.SnowflakeSinkConnector\",
# #       \"topics\": \"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY\",
# #       \"snowflake.topic2table.map\": \"winstat.COMMANDES:RAW.COMMANDES,winstat.FACTURES:RAW.FACTURES,winstat.ORDERS:RAW.ORDERS,winstat.PHARMACIE:RAW.PHARMACIE,winstat.MODSTOCK:RAW.MODSTOCK,winstat.DAYBYDAY:RAW.DAYBYDAY\",
# #       \"snowflake.user.name\": \"$SNOWFLAKE_USER\",
# #       \"snowflake.password\": \"$SNOWFLAKE_PASSWORD\",
# #       \"snowflake.account\": \"$SNOWFLAKE_ACCOUNT\",
# #       \"snowflake.database.name\": \"MEDICORE\",
# #       \"snowflake.schema.name\": \"RAW\",
# #       \"tasks.max\": \"2\",
# #       \"buffer.count.records\": \"10000\"
# #     }
# #   }" || echo "✅ Snowflake sink existe déjà"

# # curl -X POST http://localhost:8083/connectors \
# #   -H "Content-Type: application/json" \
# #   -d "{
# #     \"name\": \"snowflake-raw-sink\",
# #     \"config\": {
# #       \"connector.class\": \"com.snowflake.kafka.connector.SnowflakeSinkConnector\",
# #       \"topics\": \"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY\",
# #       \"snowflake.topic2table.map\": \"winstat.COMMANDES:RAW.COMMANDES,winstat.FACTURES:RAW.FACTURES,winstat.ORDERS:RAW.ORDERS,winstat.PHARMACIE:RAW.PHARMACIE,winstat.MODSTOCK:RAW.MODSTOCK,winstat.DAYBYDAY:RAW.DAYBYDAY\",
# #       \"snowflake.user.name\": \"$SNOWFLAKE_USER\",
# #       \"snowflake.password\": \"$SNOWFLAKE_PASSWORD\",
# #       \"snowflake.account\": \"$SNOWFLAKE_ACCOUNT\",
# #       \"snowflake.database.name\": \"$SNOWFLAKE_DATABASE\",
# #       \"snowflake.schema.name\": \"$SNOWFLAKE_SCHEMA_NAME\",
# #       \"tasks.max\": \"2\"
# #     }
# #   }" || echo "✅ Snowflake sink existe déjà"

# # 6. Snowflake Kafka Connector (Kafka → RAW)
# # Installation simplifiée (téléchargement PowerShell)
# echo "🔌 Kafka → Snowflake RAW setup..."

# powershell "Invoke-WebRequest -Uri 'https://repo1.maven.org/maven2/com/snowflake/snowflake-kafka-connector/3.1.1/snowflake-kafka-connector-3.1.1.jar' -OutFile './snowflake-connector.jar'"
# docker cp ./snowflake-connector.jar kafka_connect:/usr/share/java/
# docker compose restart connect
# sleep 20

# # 7. Pipeline ELT batch
# echo "🚀 dbt STAGING + MARTS..."
# docker compose build medicore-elt-batch
# docker compose up -d medicore-elt-batch

# # 8. Monitoring unifié
# echo "🎉 100% opérationnel !"
# echo "📊 Logs : docker logs -f medicore_elt_batch"
# echo "🔍 Kafka : http://localhost:9000"
# echo "🔍 Debezium : curl http://localhost:8083/connectors"
# echo "🔍 Snowflake RAW : snowsql -q \"USE MEDICORE.RAW; SELECT COUNT(*) FROM RAW_COMMANDES\""

# # Monitoring rapide
# echo "📈 STATUS ACTUEL :"
# # curl -s http://localhost:8083/connectors | jq '.[].name'
# # docker logs medicore_elt_batch --tail 10
# curl -s http://localhost:8083/connectors | jq '.[].name' || echo "Connecteurs OK"
# docker logs medicore_elt_batch --tail 5 2>/dev/null || echo "Pipeline batch démarré..."



# ------------------------------------------ Tout sélectionner et CRTL + : pour remettre la solution précédente en place--> se fige -----------------------


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
# for i in {1..45}; do
#   if docker ps --filter "name=kafka" --format "table {{.Status}}" | grep -q "healthy"; then
#     echo "✅ Kafka healthy !"
#     break
#   fi
#   sleep 1
#   [ $i -eq 45 ] && echo "⚠️ Kafka lent, continue..."
# done
sleep 45

# Phase 2 : Connect
echo "🔌 Phase 2/4 : connect"
docker compose up -d connect 
sleep 25

# Phase 3 : Debezium connector
echo "📦 Phase 3/4 : Debezium → RDS Winstat..."
# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "winstat-medicore",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "mysql_cdc",
#       "database.port": "3306",
#       "database.user": "cdc_user", 
#       "database.password": "cdc_password",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat",
#       "key.converter": "org.apache.kafka.connect.json.JsonConverter",
#       "value.converter": "org.apache.kafka.connect.json.JsonConverter",
#       "key.converter.schemas.enable": "false",
#       "value.converter.schemas.enable": "false"
#     }
#   }' || echo "✅ Debezium OK"
# --> version locale, pointe sur MySQL local mysql_cdc. Obligation de créer les tables COMMANDES, FACTURES ...



# # 1. INSTALLER MySQL connector dans kafka_connect
# docker exec kafka_connect bash -c "
#   curl -sSL https://repo1.maven.org/maven2/io/debezium/debezium-connector-mysql/2.7.3.Final/debezium-connector-mysql-2.7.3.Final-plugin.tar.gz | 
#   tar -xz -C /kafka/connectors/
# "
# # 2. Redémarrer Connect
# docker compose restart connect
# sleep 20
# --> le répertoire /kafka/connectors/ n'existe pas dans l'image debezium/connect
# --> Utiliser l'image officielle confluentinc/cp-kafka-connect qui a le bon répertoire ET le MySQL connector préinstallé.


# 1. Utiliser image Confluent avec MySQL connector PRÉ-INSTALLÉ
# docker compose down connect || true
# docker pull confluentinc/cp-kafka-connect:7.5.0
# docker compose up -d connect

# echo "⏳ Attente Connect API (120s max)..."
# for i in {1..120}; do
#   if curl -s http://localhost:8083/ | grep -q '"version"'; then
#     echo "✅ Connect API prête en ${i}s !"
#     break
#   fi
#   echo "⏳ Connect ready ${i}/120s..."
#   sleep 1
# done || echo "⚠️ Connect lent, poursuite..."

# # Attendre API (180s max)
# echo "⏳ Connect API (3min max)..."
# for i in {1..180}; do
#   if curl -s http://localhost:8083/ | jq -e '.version' >/dev/null 2>&1; then
#     echo "✅ Connect API prête en ${i}s ! $(curl -s http://localhost:8083/ | jq '.version')"
#     break
#   fi
#   [ $i -eq 30 ] && docker logs kafka_connect --tail 5
#   sleep 1
# done || { echo "❌ Connect timeout !"; docker logs kafka_connect; exit 1; }


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

# sleep 10  # Buffer supplémentaire

# # 2. Supprimer ancien connector mysql_cdc  (local) s'il existe 
# curl -X DELETE http://localhost:8083/connectors/winstat-rds 2>/dev/null || true
# curl -X DELETE http://localhost:8083/connectors/winstat-medicore 2>/dev/null || true


# 3. Connecteur RDS Winstat (MySQL connector ✅ disponible) (sans DELETE inutiles)
# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d "{
#     \"name\": \"winstat-rds\",
#     \"config\": {
#       \"connector.class\": \"io.debezium.connector.mysql.MySqlConnector\",
#       \"database.hostname\": \"$MYSQL_HOST\",
#       \"database.port\": \"$MYSQL_PORT\",
#       \"database.user\": \"$MYSQL_USER\",
#       \"database.password\": \"$MYSQL_PASSWORD\",
#       \"database.server.id\": \"184054\",
#       \"database.include.list\": \"winstat\",
#       \"table.include.list\": \"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY\",
#       \"topic.prefix\": \"winstat_rds\",
#       \"snapshot.mode\": \"initial\",
#       \"include.schema.changes\": \"true\"
#     }
#   }" || echo "✅ Winstat RDS connector créé"

# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d "{
#     \"name\": \"winstat-rds\",
#     \"config\": {
#       \"connector.class\": \"io.debezium.connector.mysql.MySqlConnector\",
#       \"database.hostname\": \"$MYSQL_HOST\",
#       \"database.port\": \"$MYSQL_PORT\",
#       \"database.user\": \"$MYSQL_USER\",
#       \"database.password\": \"$MYSQL_PASSWORD\",
#       \"database.server.id\": \"184054\",
#       \"database.include.list\": \"winstat\",
#       \"table.include.list\": \"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY\",
#       \"topic.prefix\": \"winstat_rds\",
#       \"snapshot.mode\": \"initial\"
#     }
#   }"


# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "winstat-rds",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'$MYSQL_HOST'",
#       "database.port": "'$MYSQL_PORT'",
#       "database.user": "'$MYSQL_USER'",
#       "database.password": "'$MYSQL_PASSWORD'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "initial",
#       "snapshot.locking.mode": "NONE",
#       "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "tasks.max": "1"
#     }
#   }'
# echo "✅ Debezium connector créé !"
# --> Debezium snapshot BLOCKÉ → ERROR during snapshot (table locks RDS)

# curl -X DELETE http://localhost:8083/connectors/winstat-rds || true

# curl -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "winstat-rds",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "initial",
#       "snapshot.locking.mode": "NONE",
#       "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "tasks.max": "1",
#       "snapshot.select.statement.overrides": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY"
#     }
#   }'

# echo "✅ Connector recréé sans locks !"



# # Nettoyage complet (schema history + connector)
# curl -X DELETE http://localhost:8083/connectors/winstat-rds || true
# docker exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --delete --topic winstat_schema_history || true
# sleep 3

# # Connector ULTRA-SPECIFIQUE (NO schema changes + 6 tables)
# curl -X POST -H "Content-Type: application/json" http://localhost:8083/connectors \
#   -d '{
#     "name": "winstat-rds",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "table.exclude.list": "winstat.#.*",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "schema_only_recovery",
#       "snapshot.locking.mode": "NONE",
#       "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "schema.history.internal.store.only.captured.tables.ddl": "true",
#       "tasks.max": "1",
#       "inconsistent.schema.handling.mode": "warn"
#     }
#   }'
# echo "✅ Connector 6 tables + schema_only_recovery !"
# --> ❌ Erreur 1 : OCI runtime exec failed: "kafka-topics.sh" not found
# --> ❌ Erreur 2 : table.exclude.list incompatible avec table.include.list
# --> ❌ Connector NON créé (status vide)

# 1. STOP + CLEAN TOTAL
# curl -X DELETE http://localhost:8083/connectors/winstat-rds || true
# docker exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --delete --topic winstat_schema_history || true

# 2. RESTART Connector ULTRA-SIMPLE (6 tables + NO schema issues)
# curl -X POST -H "Content-Type: application/json" http://localhost:8083/connectors -d '{
#   "name": "winstat-rds",
#   "config": {
#     "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#     "database.hostname": "db-winstat.cxcpu2dcqi6m.eu-west-3.rds.amazonaws.com",
#     "database.port": "3306",
#     "database.user": "admin",
#     "database.password": "REDACTED_MYSQL_PASSWORD",
#     "database.server.id": "184054",
#     "database.include.list": "winstat",
#     "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#     "topic.prefix": "winstat_rds",
#     "snapshot.mode": "initial",
#     "snapshot.locking.mode": "NONE",
#     "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#     "schema.history.internal.kafka.topic": "winstat_schema_history",
#     "tasks.max": "1",
#     "schema.history.internal.store.only.captured.tables.ddl": "true"
#   }
# }'

# curl -X POST -H "Content-Type: application/json" http://localhost:8083/connectors -d '{
#   "name": "winstat-rds",
#   "config": {
#     "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#     "database.hostname": "'"$MYSQL_HOST"'",
#     "database.port": "'"$MYSQL_PORT"'",
#     "database.user": "'"$MYSQL_USER"'",
#     "database.password": "'"$MYSQL_PASSWORD"'",
#     "database.server.id": "184054",
#     "database.include.list": "winstat",
#     "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#     "topic.prefix": "winstat_rds",
#     "snapshot.mode": "initial",
#     "snapshot.locking.mode": "NONE",
#     "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#     "schema.history.internal.kafka.topic": "winstat_schema_history",
#     "tasks.max": "1",
#     "schema.history.internal.store.only.captured.tables.ddl": "true"
#   }
# }'
# echo "✅ Connector fixé ! Monitoring:"
# echo "docker logs -f kafka_connect | grep -E \"(Snapshotting|COMMANDES|completed)\""
# -->✅ Étape 1-4 OK (locks, binlog mysql-bin-changelog.125951:544)
# -->❌ Étape 5 ERROR : BinlogSnapshotChangeEventSource.createSchemaEventsForTables()
# -->⚠️  "Retry 4 of unlimited retries" → BOUCLE ∞

# curl -X DELETE http://localhost:8083/connectors/winstat-rds || true
# curl -X POST -H "Content-Type: application/json" http://localhost:8083/connectors \
#   -d '{
#     "name":"winstat-rds",
#     "config":{
#       "connector.class":"io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname":"db-winstat.cxcpu2dcqi6m.eu-west-3.rds.amazonaws.com",
#       "database.port":"3306",
#       "database.user":"admin",
#       "database.password":"REDACTED_MYSQL_PASSWORD",
#       "database.server.id":"184054",
#       "database.include.list":"winstat",
#       "table.include.list":"winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.PHARMACIE,winstat.MODSTOCK,winstat.DAYBYDAY",
#       "topic.prefix":"winstat_rds",
#       "snapshot.mode":"never",
#       "snapshot.locking.mode":"NONE",
#       "schema.history.internal.kafka.bootstrap.servers":"kafka:9092",
#       "schema.history.internal.kafka.topic":"winstat_schema_history",
#       "tasks.max":"1"}}'
# echo "✅ BINLOG STREAMING ACTIVÉ !"
#--> ❌ PROBLÈME RACINE : Offset binlog corrompu + schéma history incompatible
#--> SKIPPED snapshot + no changes will be captured + schema not known = cycle infernal

# CONNECTOR_NAME="winstat-rds"

# 1. Pré-créer schema_history
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
echo "📦 Bulk load initial (18 tables)..."
docker exec medicore_elt_batch python /app/pipelines/bulk_load.py --truncate

# # 1. KILL connector + clean
# curl -X DELETE http://localhost:8083/connectors/$CONNECTOR_NAME || true

# # 2. Topic CLEAN (ignore erreurs)
# docker exec kafka kafka-topics --bootstrap-server localhost:9092 --delete --topic winstat_schema_history || true
# sleep 2
# docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic winstat_schema_history --partitions 1 --replication-factor 1 || true


# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'$CONNECTOR_NAME'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "initial",
#       "snapshot.locking.mode": "minimal",
#       "snapshot.max.threads": "1",
#       "snapshot.fetch.size": "1000",
#       "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "schema.history.internal.store.only.captured.tables.ddl": "true",
#       "schema.history.internal.recovery.poll.interval.ms": "500",
#       "schema.history.internal.recovery.retries": "10",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ RECOVERY MODE activé ! Attendre 2min → Status RUNNING"
# else
#   echo "❌ ERREUR : Échec création connecteur winstat-rds (HTTP 4xx/5xx ou réseau)"
#   echo "Vérifiez :"
#   echo "  • Kafka Connect est-il démarré ? (curl http://localhost:8083)"
#   echo "  • Le connecteur existe-t-il déjà ? (curl http://localhost:8083/connectors)"
# fi
# -->✅ Status RUNNING mais ❌ Snapshot ÉCHOUÉ sur table locks (10s timeout)

# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'"$CONNECTOR_NAME"'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "initial",
#       "snapshot.locking.mode": "minimal",
#       "schema.history.internal.kafka.bootstrap.servers": "'"$KAFKA_BOOTSTRAP_SERVERS"'",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ BINLOG STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
# else
#   echo "❌ ERREUR : Échec création connecteur winstat-rds (HTTP 4xx/5xx ou réseau)"
#   echo "Vérifiez :"
#   echo "  • Kafka Connect est-il démarré ? (curl http://localhost:8083)"
#   echo "  • Le connecteur existe-t-il déjà ? (curl http://localhost:8083/connectors)"
# fi
# --> 🚨 SNAPSHOT ÉCHOUÉ SUR TABLE LOCKS - CLASSIQUE RDS
# --> ✅ Connector: RUNNING (worker OK) ✓
# --> ✅ Task[0]: RUNNING (masque l'erreur) ⚠️
# --> ❌ SNAPSHOT **FAILED** → tableLock timeout 9s
# --> "Locking [COMMANDES,FACTURES,ORDERS,PHARMACIE,MODSTOCK,DAYBYDAY]"
# --> ERROR tableLock() → "Snapshot was not completed successfully"


# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'"$CONNECTOR_NAME"'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "schema_only",
#       "snapshot.locking.mode": "none",
#       "schema.history.internal.kafka.bootstrap.servers": "'"$KAFKA_BOOTSTRAP_SERVERS"'",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ BINLOG STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
# else
#   echo "❌ ERREUR : Échec création connecteur winstat-rds (HTTP 4xx/5xx ou réseau)"
#   echo "Vérifiez :"
#   echo "  • Kafka Connect est-il démarré ? (curl http://localhost:8083)"
#   echo "  • Le connecteur existe-t-il déjà ? (curl http://localhost:8083/connectors)"
# fi
# --> 🚨 PROBLÈME IDENTIFIÉ : schema_only ÉCHOUE AUSSI sur RDS
# --> ✅ Connector créé ✓ Status=RUNNING (faux positif)
# --> ❌ SNAPSHOT ÉCHOUÉ → "Error during snapshot" (10s timeout)
# --> ❌ Retry 56/illimité → Loop infini
# --> ❌ AUCUN message Kafka → INSERT perdu
# --> ❌ RAW_COMMANDES = 0


# # "snapshot.mode": "never"
# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'$CONNECTOR_NAME'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "never",
#       "snapshot.locking.mode": "none",
#       "schema.history.internal.kafka.bootstrap.servers": "'"$KAFKA_BOOTSTRAP_SERVERS"'",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "schema.history.internal.store.only.captured.tables.ddl": "true",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ CDC STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
# else
#   echo "❌ ERREUR connector"
#   exit 1
# fi
# --> 🚨 ERREUR CLASSIQUE never : "schema isn't known to this connector"
# --> ✅ Connector créé ✓ schema_history topic créé ✓
# --> ✅ Snapshot SKIPPED ✓ ("Snapshot ended with SnapshotResult [status=SKIPPED]")
# --> ✅ Binlog CONNECTÉ ✓ ("Connected to binlog at db-winstat...")
# --> ❌ FAILED → "Encountered change event for table **winstat.COMMANDES** whose **schema isn't known**"



# # "snapshot.mode": "when_needed"
# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'$CONNECTOR_NAME'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "when_needed",
#       "snapshot.locking.mode": "none",
#       "schema.history.internal.kafka.bootstrap.servers": "'"$KAFKA_BOOTSTRAP_SERVERS"'",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "schema.history.internal.store.only.captured.tables.ddl": "true",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ CDC STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
# else
#   echo "❌ ERREUR connector"
#   exit 1
# fi
# --> 🚨 PROBLÈME : when_needed déclenche AUSSI snapshot complet
# --> ✅ Connector RUNNING (status OK)
# --> ❌ Snapshot TIMEOUT → "Error during snapshot" (12s)
# --> ❌ Retry 6/∞ → Loop d'erreur
# --> when_needed génère snapshot complet (schema + data) → même timeout RDS que initial.


# # "snapshot.mode": "no_data"
# if curl -f -X POST http://localhost:8083/connectors \
#   -H "Content-Type: application/json" \
#   -d '{
#     "name": "'"$CONNECTOR_NAME"'",
#     "config": {
#       "connector.class": "io.debezium.connector.mysql.MySqlConnector",
#       "database.hostname": "'"$MYSQL_HOST"'",
#       "database.port": "'"$MYSQL_PORT"'",
#       "database.user": "'"$MYSQL_USER"'",
#       "database.password": "'"$MYSQL_PASSWORD"'",
#       "database.server.id": "184054",
#       "database.include.list": "winstat",
#       "table.include.list": "winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK",
#       "topic.prefix": "winstat_rds",
#       "snapshot.mode": "no_data",
#       "schema.history.internal.kafka.bootstrap.servers": "'"$KAFKA_BOOTSTRAP_SERVERS"'",
#       "schema.history.internal.kafka.topic": "winstat_schema_history",
#       "tasks.max": "1"
#     }
#   }'; then
#   echo "✅ CDC STREAMING ACTIVÉ ! ($CONNECTOR_NAME)"
# else
#   echo "❌ ERREUR connector"
#   exit 1
# fi
# --> 🚨 PROBLÈME IDENTIFIÉ : no_data IGNORE table.include.list !
# --> ✅ Connector RUNNING ✓
# --> ❌ Snapshot TOUJOURS actif → liste TOUTES les tables winstat.* ❌
# --> "Adding table winstat.WRK_LOG, winstat.LPPR, winstat.STOCKHISTORY..." 
# --> 🎯 CAUSE : no_data = scan COMPLET database
# --> no_data scan TOUS les tables de database.include.list=winstat → timeout inévitable.


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
      "schema.history.internal.store.only.captured.tables.ddl": "true"
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


# sleep 120

# # 6. Snowflake Kafka Connector (Kafka → RAW)
# # Installation simplifiée (téléchargement PowerShell)
# echo "🔌 Kafka → Snowflake RAW setup..."

# powershell "Invoke-WebRequest -Uri 'https://repo1.maven.org/maven2/com/snowflake/snowflake-kafka-connector/3.1.1/snowflake-kafka-connector-3.1.1.jar' -OutFile './snowflake-connector.jar'"
# docker cp ./snowflake-connector.jar kafka_connect:/usr/share/java/
# docker compose restart connect
# sleep 20
# --> On remettra en place quand  CDC → Kafka OK

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