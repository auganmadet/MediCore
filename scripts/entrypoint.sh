#!/bin/bash
set -euo pipefail

echo "🚀 MediCore Entrypoint - $(date) - ENV: $ENV"

# 1. Vérifier variables d'environnement Snowflake obligatoires
: "${SNOWFLAKE_ACCOUNT:?Error: SNOWFLAKE_ACCOUNT manquant}"
: "${SNOWFLAKE_USER:?Error: SNOWFLAKE_USER manquant}"
: "${SNOWFLAKE_PASSWORD:?Error: SNOWFLAKE_PASSWORD manquant}"

# 2. Attendre services dépendants : Kafka (9092) + MySQL (3306)
echo "⏳ Waiting for dependencies (Kafka/MySQL)..."
python -c "
import time, socket
services = [('kafka', 9092), ('mysql_cdc', 3306)]
for host, port in services:
    start = time.time()
    while time.time() - start < 120:
        try:
            socket.create_connection((host, port), 2)
            print(f'✅ {host}:{port} ready')
            break
        except:
            time.sleep(2)
        else:
            print(f'❌ {host}:{port} timeout')
            exit(1)
"

# 3. Lancer le script passé en argument (command: ./scripts/batch_loop.sh dans docker-compose.yml)
exec "$@"
