#!/bin/bash

#Version ancienne (Python local) sans Docker
# à supprimer par la suite

echo "🏗️  Setup MediCore ELT Pipeline"

# 1. Installation dépendances
pip install -r requirements.txt
dbt deps

# 2. DDL Snowflake (si pas déjà fait)
echo "💾 Création objets Snowflake (RAW tables + rôles)..."
psql -f sql/create_snowflake_objects.sql  # À adapter

# 3. Test connexions
echo "🔌 Test connexions..."
python -c "from utils.snowflake_connector import SnowflakeConnector; SnowflakeConnector().test_connection()"

# 4. Premier run dbt
echo "🚀 Premier run dbt RAW+STAGING..."
dbt run --select +raw +stg_pharmacie +stg_produits

echo "✅ Setup terminé ! Exécute './run_pipeline.sh dev' pour lancer le pipeline."
