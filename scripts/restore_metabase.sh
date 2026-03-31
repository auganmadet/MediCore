#!/bin/bash
# restore_metabase.sh — Restaurer un backup PostgreSQL Metabase
# Usage : bash scripts/restore_metabase.sh [fichier_backup]
# Sans argument : restaure le backup le plus recent

set -euo pipefail

BACKUP_DIR="/app/backups/metabase"

# Variables PostgreSQL
PG_HOST="${METABASE_DB_HOST:-metabase_db}"
PG_PORT="${METABASE_DB_PORT:-5432}"
PG_DB="${METABASE_DB_NAME:-metabase}"
PG_USER="${METABASE_DB_USER:-metabase}"
export PGPASSWORD="${METABASE_DB_PASSWORD:-metabase_dev}"

# Determiner le fichier a restaurer
if [ -n "${1:-}" ]; then
  BACKUP_FILE="$1"
else
  BACKUP_FILE=$(ls -t "$BACKUP_DIR"/metabase_*.sql.gz 2>/dev/null | head -1)
  if [ -z "$BACKUP_FILE" ]; then
    echo "Aucun backup trouve dans $BACKUP_DIR"
    exit 1
  fi
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Fichier introuvable: $BACKUP_FILE"
  exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Restore Metabase: $BACKUP_FILE ($SIZE)"
echo ""
echo "ATTENTION: cette operation va REMPLACER toute la base Metabase actuelle."
echo "  - Arreter Metabase avant: docker compose stop metabase"
echo "  - Redemarrer apres: docker compose start metabase"
echo ""
read -p "Continuer ? (oui/non) " confirm
if [ "$confirm" != "oui" ]; then
  echo "Annule."
  exit 0
fi

# Drop + recreate la base
echo "Drop et recreation de la base $PG_DB..."
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${PG_DB};" \
  -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER};"

# Restaurer le dump
echo "Restauration en cours..."
gunzip -c "$BACKUP_FILE" | psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
  --quiet

echo "Restore Metabase: OK"
echo "Redemarrer Metabase: docker compose start metabase"

unset PGPASSWORD
