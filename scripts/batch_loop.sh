#!/bin/bash
set -euo pipefail

# Intervalle entre batches : 5 min en dev, 30 min en prod (surchargeable via BATCH_INTERVAL_MIN)
if [ "${ENV}" = "prod" ]; then
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-30}
else
  INTERVAL_MIN=${BATCH_INTERVAL_MIN:-5}
fi
LOCK_FILE="/tmp/bulk_load.lock"
REF_DONE_FLAG="/tmp/ref_bulk_done_today"
REF_RELOAD_HOUR=${REF_RELOAD_HOUR:-03}

# Alerting Teams (optionnel : si TEAMS_WEBHOOK_URL est vide, les erreurs sont loguees sans alerte)
ALERT_THRESHOLD=${ALERT_THRESHOLD:-3}
REF_FAIL=0; CDC_FAIL=0; STG_FAIL=0; MARTS_FAIL=0; TEST_FAIL=0; FRESH_FAIL=0

send_teams_alert() {
  local component="$1" fail_count="$2" status="${3:-failure}"
  [ -z "${TEAMS_WEBHOOK_URL:-}" ] && return 0

  if [ "$status" = "recovery" ]; then
    local color="Good"
    local title="MediCore : $component fonctionne a nouveau"
    local text="Apres $fail_count echecs consecutifs sur **${ENV}**."
  else
    local color="Attention"
    local title="ALERTE MediCore : $component a echoue $fail_count fois"
    local text="Echecs consecutifs sur **${ENV}**. Verifier les logs du conteneur medicore_elt_batch."
  fi

  local payload="{
      \"type\": \"message\",
      \"attachments\": [{
        \"contentType\": \"application/vnd.microsoft.card.adaptive\",
        \"content\": {
          \"type\": \"AdaptiveCard\",
          \"version\": \"1.2\",
          \"body\": [
            {\"type\": \"TextBlock\", \"text\": \"$title\", \"weight\": \"Bolder\", \"color\": \"$color\", \"size\": \"Medium\"},
            {\"type\": \"TextBlock\", \"text\": \"$text\", \"wrap\": true}
          ]
        }
      }]
    }"

  local max_retries=3
  for attempt in $(seq 1 $max_retries); do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$TEAMS_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "$payload" --connect-timeout 10 --max-time 15)
    if [ "$http_code" = "200" ] || [ "$http_code" = "202" ]; then
      return 0
    fi
    echo "Teams webhook attempt $attempt/$max_retries failed (HTTP $http_code)"
    sleep $((attempt * 5))
  done
  echo "Warning: Teams webhook failed after $max_retries attempts"
}

echo "MediCore Batch Loop - ${INTERVAL_MIN}min - ENV: ${ENV} - ref reload at ${REF_RELOAD_HOUR}h"

# En dev : mode single-run (pas de boucle infinie)
if [ "${ENV}" = "dev" ] && [ "${BATCH_LOOP:-true}" = "false" ]; then
  echo "Dev mode: boucle desactivee (BATCH_LOOP=false). Lancer manuellement chaque composant."
  exit 0
fi

while true; do
  echo "$(date) - Debut batch #$(date +%H%M)"

  # Verifier qu'un bulk load n'est pas en cours
  if [ -f "$LOCK_FILE" ]; then
    echo "Bulk load en cours (lock: $LOCK_FILE) - batch skippe"
    sleep $((INTERVAL_MIN * 60))
    continue
  fi

  # 0. Re-bulk quotidien des 14 tables reference (1x/jour a ${REF_RELOAD_HOUR}h)
  HOUR=$(date +%H)
  if [ "$HOUR" = "$REF_RELOAD_HOUR" ] && [ ! -f "$REF_DONE_FLAG" ]; then
    echo "Phase ref-reload: 14 tables reference (truncate + bulk load)"
    if python /app/pipelines/bulk_load.py --ref-only --truncate; then
      [ $REF_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL" "recovery"
      REF_FAIL=0
      touch "$REF_DONE_FLAG"
    else
      REF_FAIL=$((REF_FAIL + 1))
      echo "Ref-reload failed ($REF_FAIL consecutive)"
      [ $REF_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL"
    fi
  fi
  [ "$HOUR" = "00" ] && rm -f "$REF_DONE_FLAG"

  # 1. CDC (Kafka -> Snowflake RAW)
  echo "Phase CDC"
  if python /app/pipelines/daily_cdc_batch.py; then
    [ $CDC_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "CDC batch" "$CDC_FAIL" "recovery"
    CDC_FAIL=0
  else
    CDC_FAIL=$((CDC_FAIL + 1))
    echo "CDC failed ($CDC_FAIL consecutive)"
    [ $CDC_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "CDC batch" "$CDC_FAIL"
  fi

  # 2. DBT pipeline
  echo "Phase dbt"
  cd /app/dbt

  if dbt run --select tag:staging --target $ENV; then
    [ $STG_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt staging" "$STG_FAIL" "recovery"
    STG_FAIL=0
  else
    STG_FAIL=$((STG_FAIL + 1))
    echo "dbt staging failed ($STG_FAIL consecutive)"
    [ $STG_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt staging" "$STG_FAIL"
  fi

  if dbt run --select tag:marts --target $ENV; then
    [ $MARTS_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt marts" "$MARTS_FAIL" "recovery"
    MARTS_FAIL=0
  else
    MARTS_FAIL=$((MARTS_FAIL + 1))
    echo "dbt marts failed ($MARTS_FAIL consecutive)"
    [ $MARTS_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt marts" "$MARTS_FAIL"
  fi

  if dbt test --select stg_* --target $ENV; then
    [ $TEST_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt test" "$TEST_FAIL" "recovery"
    TEST_FAIL=0
  else
    TEST_FAIL=$((TEST_FAIL + 1))
    echo "dbt test failed ($TEST_FAIL consecutive)"
    [ $TEST_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt test" "$TEST_FAIL"
  fi

  # 5. Source freshness (detecte données stales même si le process tourne)
  echo "Phase freshness"
  if dbt source freshness --target $ENV; then
    [ $FRESH_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "source freshness" "$FRESH_FAIL" "recovery"
    FRESH_FAIL=0
  else
    FRESH_FAIL=$((FRESH_FAIL + 1))
    echo "source freshness failed ($FRESH_FAIL consecutive)"
    [ $FRESH_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "source freshness" "$FRESH_FAIL"
  fi

  cd /app

  echo "Batch termine - Prochain run: $(date -d "+${INTERVAL_MIN} minutes" 2>/dev/null || echo "${INTERVAL_MIN}min")"
  sleep $((INTERVAL_MIN * 60))
done
