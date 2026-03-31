#!/bin/bash
# backup_metabase.sh — Dump quotidien de la base PostgreSQL Metabase
# Usage : bash scripts/backup_metabase.sh
# Integre dans batch_loop.sh (mode nuit, 1x/jour)

set -euo pipefail

BACKUP_DIR="/app/backups/metabase"
RETENTION_DAYS=${METABASE_BACKUP_RETENTION:-30}
DATE=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="${BACKUP_DIR}/metabase_${DATE}.sql.gz"

# Variables PostgreSQL (coherentes avec docker-compose.yml)
PG_HOST="${METABASE_DB_HOST:-metabase_db}"
PG_PORT="${METABASE_DB_PORT:-5432}"
PG_DB="${METABASE_DB_NAME:-metabase}"
PG_USER="${METABASE_DB_USER:-metabase}"
export PGPASSWORD="${METABASE_DB_PASSWORD:-metabase_dev}"

mkdir -p "$BACKUP_DIR"

echo "Backup Metabase: debut (${PG_HOST}:${PG_PORT}/${PG_DB})"

# pg_dump compresse avec gzip
if pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    --no-owner --no-privileges | gzip > "$BACKUP_FILE"; then
  SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
  echo "Backup Metabase: OK -> $BACKUP_FILE ($SIZE)"
else
  echo "Backup Metabase: ECHEC"
  rm -f "$BACKUP_FILE"
  exit 1
fi

# Purge des backups > RETENTION_DAYS jours
DELETED=$(find "$BACKUP_DIR" -name "metabase_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
  echo "Backup Metabase: $DELETED ancien(s) backup(s) supprime(s) (retention ${RETENTION_DAYS}j)"
fi

unset PGPASSWORD
