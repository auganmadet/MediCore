#!/bin/bash
set -euo pipefail

# ==========================================================================
# clone_dev.sh — Re-clone MEDICORE_DEV depuis MEDICORE_PROD (zero-copy)
#
# Usage :
#   ./scripts/clone_dev.sh                  # utilise les credentials .env
#   ./scripts/clone_dev.sh --dry-run        # affiche les commandes sans exécuter
#
# Prérequis :
#   - Rôle ACCOUNTADMIN ou SYSADMIN (DROP + CREATE DATABASE)
#   - Variables d'environnement : SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
#
# Opérations :
#   1. DROP DATABASE MEDICORE_DEV (supprime l'ancien clone)
#   2. CREATE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD (zero-copy, instantané)
#   3. Re-applique les GRANTs sur MEDICORE_DEV (perdus avec le DROP)
#   4. Désactive Time Travel (inutile en dev, économie stockage)
#   5. Vérifie que le clone est fonctionnel (compte les schémas)
# ==========================================================================

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  echo "[DRY-RUN] Les commandes SQL seront affichées mais pas exécutées."
fi

# Charger .env si disponible (ignore les lignes invalides)
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r line; do
    # Ignorer commentaires et lignes vides
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$line" ]] && continue
    # Extraire KEY=VALUE (ignorer les lignes sans =)
    [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}" 2>/dev/null || true
  done < "$ENV_FILE"
fi

# Vérifier les credentials
for var in SNOWFLAKE_ACCOUNT SNOWFLAKE_USER SNOWFLAKE_PASSWORD; do
  if [ -z "${!var:-}" ]; then
    echo "ERREUR: variable $var non définie. Vérifier .env ou l'environnement."
    exit 1
  fi
done

SQL_STATEMENTS=(
  "-- 1. Supprimer l'ancien clone"
  "DROP DATABASE IF EXISTS MEDICORE_DEV;"

  "-- 2. Créer le nouveau clone (zero-copy, instantané)"
  "CREATE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD;"

  "-- 3. Re-appliquer les GRANTs (perdus avec le DROP)"
  "GRANT ALL ON DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR;"
  "GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR;"

  "-- 4. Désactiver Time Travel (inutile en dev, économie stockage)"
  "ALTER DATABASE MEDICORE_DEV SET DATA_RETENTION_TIME_IN_DAYS = 0;"

  "-- 5. Vérification"
  "SELECT SCHEMA_NAME FROM MEDICORE_DEV.INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME;"
)

if [ $DRY_RUN -eq 1 ]; then
  echo ""
  echo "=== Commandes SQL qui seraient exécutées ==="
  for stmt in "${SQL_STATEMENTS[@]}"; do
    echo "  $stmt"
  done
  echo ""
  echo "[DRY-RUN] Aucune commande exécutée."
  exit 0
fi

echo "=== Re-clone MEDICORE_DEV depuis MEDICORE_PROD ==="
echo "  Account : ${SNOWFLAKE_ACCOUNT:0:8}***"
echo "  User    : ${SNOWFLAKE_USER}"
echo ""

# Exécuter les commandes SQL via Python (snowflake-connector)
python3 -c "
import snowflake.connector, os, sys

conn = snowflake.connector.connect(
    account=os.getenv('SNOWFLAKE_ACCOUNT'),
    user=os.getenv('SNOWFLAKE_USER'),
    password=os.getenv('SNOWFLAKE_PASSWORD'),
    role='ACCOUNTADMIN',
    warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
)
cur = conn.cursor()

try:
    print('1/4 DROP DATABASE MEDICORE_DEV...')
    cur.execute('DROP DATABASE IF EXISTS MEDICORE_DEV')
    print('     OK')

    print('2/4 CREATE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD...')
    cur.execute('CREATE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD')
    print('     OK (zero-copy, instantané)')

    print('3/5 GRANTs sur MEDICORE_DEV...')
    cur.execute('GRANT ALL ON DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR')
    cur.execute('GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR')
    print('     OK')

    print('4/5 Désactivation Time Travel (inutile en dev, économie stockage)...')
    cur.execute('ALTER DATABASE MEDICORE_DEV SET DATA_RETENTION_TIME_IN_DAYS = 0')
    print('     OK (DATA_RETENTION_TIME_IN_DAYS = 0)')

    print('5/5 Vérification...')
    cur.execute('SELECT SCHEMA_NAME FROM MEDICORE_DEV.INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME')
    schemas = [r[0] for r in cur.fetchall()]
    print(f'     Schémas trouvés : {schemas}')

    expected = {'RAW', 'STAGING', 'MARTS', 'AUDIT', 'SNAPSHOTS', 'INFORMATION_SCHEMA', 'PUBLIC'}
    missing = expected - set(schemas)
    if missing:
        print(f'     ATTENTION : schémas manquants : {missing}')
        sys.exit(1)
    else:
        print('     Tous les schémas attendus sont présents.')

    print()
    print('Re-clone MEDICORE_DEV terminé avec succès.')

except Exception as e:
    print(f'ERREUR: {e}', file=sys.stderr)
    sys.exit(1)
finally:
    cur.close()
    conn.close()
"
