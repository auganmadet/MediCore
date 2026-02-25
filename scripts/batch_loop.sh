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
REF_FAIL=0; CDC_FAIL=0; STG_FAIL=0; SNAP_FAIL=0; MARTS_FAIL=0; TEST_FAIL=0; FRESH_FAIL=0; ZERO_VOL=0

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

send_dbt_run_summary() {
  local phase="$1"
  local results_file="/app/dbt/target/run_results.json"
  [ ! -f "$results_file" ] && return 0
  [ -z "${TEAMS_WEBHOOK_URL:-}" ] && return 0

  # Parse run_results.json avec Python (jq non dispo dans l'image)
  local summary
  summary=$(python3 -c "
import json
with open('$results_file') as f:
    data = json.load(f)
results = data.get('results', [])
elapsed = data.get('elapsed_time', 0)
counts = {}
for r in results:
    s = r.get('status', 'unknown')
    counts[s] = counts.get(s, 0) + 1
total = len(results)
ok = counts.get('pass', 0) + counts.get('success', 0)
warn = counts.get('warn', 0)
err = counts.get('error', 0) + counts.get('fail', 0)
skip = counts.get('skip', 0)
print(f'{total}|{ok}|{warn}|{err}|{skip}|{elapsed:.1f}')
" 2>/dev/null) || return 0

  IFS='|' read -r total ok warn err skip elapsed <<< "$summary"

  # Alerte Teams uniquement si warnings ou erreurs
  [ "$warn" = "0" ] && [ "$err" = "0" ] && return 0

  if [ "$err" != "0" ]; then
    local color="Attention"
    local title="dbt $phase : $err erreur(s) sur ${ENV}"
  else
    local color="Warning"
    local title="dbt $phase : $warn warning(s) sur ${ENV}"
  fi
  local text="pass=$ok warn=$warn error=$err skip=$skip — ${elapsed}s — ${total} models/tests"

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

  curl -s -o /dev/null -X POST "$TEAMS_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "$payload" --connect-timeout 10 --max-time 15 > /dev/null 2>&1
}

echo "MediCore Batch Loop - ${INTERVAL_MIN}min - ENV: ${ENV} - ref reload at ${REF_RELOAD_HOUR}h"

# En dev : mode single-run (pas de boucle infinie)
if [ "${ENV}" = "dev" ] && [ "${BATCH_LOOP:-true}" = "false" ]; then
  echo "Dev mode: boucle desactivee (BATCH_LOOP=false). Lancer manuellement chaque composant."
  exit 0
fi

while true; do
  echo "$(date) - Debut batch #$(date +%H%M)"

  # Générer un RUN_ID unique pour cette itération (lineage opérationnel)
  RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
  export RUN_ID
  echo "RUN_ID: $RUN_ID"
  python3 -c "from pipelines.utils.audit import log_run_start; log_run_start('$RUN_ID', '${ENV}')" 2>/dev/null || true

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
    python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'ref_reload')" 2>/dev/null || true
    if python /app/pipelines/bulk_load.py --ref-only --truncate --run-id "$RUN_ID"; then
      python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'SUCCESS')" 2>/dev/null || true
      [ $REF_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL" "recovery"
      REF_FAIL=0
      touch "$REF_DONE_FLAG"
    else
      python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'FAILED', error='Ref-reload failed')" 2>/dev/null || true
      REF_FAIL=$((REF_FAIL + 1))
      echo "Ref-reload failed ($REF_FAIL consecutive)"
      [ $REF_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL"
    fi
  fi
  [ "$HOUR" = "00" ] && rm -f "$REF_DONE_FLAG"

  # Rétention audit : purge données > 90 jours (1x/jour a 01h)
  if [ "$HOUR" = "01" ] && [ ! -f "/tmp/audit_purge_done_today" ]; then
    echo "Phase audit-purge: retention 90 jours"
    python3 -c "
from pipelines.utils.audit import _get_audit_conn
conn = _get_audit_conn()
cur = conn.cursor()
cur.execute(\"DELETE FROM PIPELINE_RUNS WHERE RUN_START < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.execute(\"DELETE FROM PIPELINE_STEP_RUNS WHERE STEP_START < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.execute(\"DELETE FROM DBT_MODEL_RUNS WHERE CREATED_AT < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.close()
conn.close()
print('Audit purge terminee')
" 2>/dev/null || echo "Audit purge failed (non bloquant)"
    touch "/tmp/audit_purge_done_today"
  fi
  [ "$HOUR" = "02" ] && rm -f "/tmp/audit_purge_done_today"

  # 1. CDC (Kafka -> Snowflake RAW)
  echo "Phase CDC"
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'cdc_batch')" 2>/dev/null || true
  if python /app/pipelines/daily_cdc_batch.py --run-id "$RUN_ID"; then
    CDC_COUNT=$(cat /tmp/cdc_last_count 2>/dev/null || echo "0")
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'cdc_batch', 'SUCCESS', ${CDC_COUNT})" 2>/dev/null || true
    [ $CDC_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "CDC batch" "$CDC_FAIL" "recovery"
    CDC_FAIL=0

    # Volume check : alerte si 0 events inseres N fois consecutives
    if [ "$CDC_COUNT" = "0" ]; then
      ZERO_VOL=$((ZERO_VOL + 1))
      echo "CDC volume: 0 events ($ZERO_VOL consecutive)"
      [ $ZERO_VOL -eq $ALERT_THRESHOLD ] && send_teams_alert "CDC volume (0 events)" "$ZERO_VOL"
    else
      [ $ZERO_VOL -ge $ALERT_THRESHOLD ] && send_teams_alert "CDC volume" "$ZERO_VOL" "recovery"
      ZERO_VOL=0
      echo "CDC volume: $CDC_COUNT events"
    fi
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'cdc_batch', 'FAILED', error='CDC batch failed')" 2>/dev/null || true
    CDC_FAIL=$((CDC_FAIL + 1))
    echo "CDC failed ($CDC_FAIL consecutive)"
    [ $CDC_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "CDC batch" "$CDC_FAIL"
  fi

  # 2. DBT pipeline
  echo "Phase dbt"
  cd /app/dbt

  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_staging')" 2>/dev/null || true
  if dbt run --select tag:staging --target $ENV --vars "{run_id: '$RUN_ID'}"; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_staging', 'SUCCESS')" 2>/dev/null || true
    [ $STG_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt staging" "$STG_FAIL" "recovery"
    STG_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_staging', 'FAILED', error='dbt staging failed')" 2>/dev/null || true
    STG_FAIL=$((STG_FAIL + 1))
    echo "dbt staging failed ($STG_FAIL consecutive)"
    [ $STG_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt staging" "$STG_FAIL"
  fi
  send_dbt_run_summary "staging"

  # 3. Snapshots SCD2 (apres staging, avant marts)
  echo "Phase snapshots"
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_snapshot')" 2>/dev/null || true
  if dbt snapshot --target $ENV --vars "{run_id: '$RUN_ID'}"; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_snapshot', 'SUCCESS')" 2>/dev/null || true
    [ $SNAP_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt snapshot" "$SNAP_FAIL" "recovery"
    SNAP_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_snapshot', 'FAILED', error='dbt snapshot failed')" 2>/dev/null || true
    SNAP_FAIL=$((SNAP_FAIL + 1))
    echo "dbt snapshot failed ($SNAP_FAIL consecutive)"
    [ $SNAP_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt snapshot" "$SNAP_FAIL"
  fi

  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_marts')" 2>/dev/null || true
  if dbt run --select tag:marts --target $ENV --vars "{run_id: '$RUN_ID'}"; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_marts', 'SUCCESS')" 2>/dev/null || true
    [ $MARTS_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt marts" "$MARTS_FAIL" "recovery"
    MARTS_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_marts', 'FAILED', error='dbt marts failed')" 2>/dev/null || true
    MARTS_FAIL=$((MARTS_FAIL + 1))
    echo "dbt marts failed ($MARTS_FAIL consecutive)"
    [ $MARTS_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt marts" "$MARTS_FAIL"
  fi
  send_dbt_run_summary "marts"

  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_test')" 2>/dev/null || true
  if dbt test --select stg_* --target $ENV --vars "{run_id: '$RUN_ID'}"; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_test', 'SUCCESS')" 2>/dev/null || true
    [ $TEST_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt test" "$TEST_FAIL" "recovery"
    TEST_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_test', 'FAILED', error='dbt test failed')" 2>/dev/null || true
    TEST_FAIL=$((TEST_FAIL + 1))
    echo "dbt test failed ($TEST_FAIL consecutive)"
    [ $TEST_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt test" "$TEST_FAIL"
  fi
  send_dbt_run_summary "test"

  # 5. Source freshness (detecte données stales même si le process tourne)
  echo "Phase freshness"
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'freshness')" 2>/dev/null || true
  if dbt source freshness --target $ENV; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'freshness', 'SUCCESS')" 2>/dev/null || true
    [ $FRESH_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "source freshness" "$FRESH_FAIL" "recovery"
    FRESH_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'freshness', 'FAILED', error='source freshness failed')" 2>/dev/null || true
    FRESH_FAIL=$((FRESH_FAIL + 1))
    echo "source freshness failed ($FRESH_FAIL consecutive)"
    [ $FRESH_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "source freshness" "$FRESH_FAIL"
  fi

  cd /app

  # Statut global du run
  if [ $CDC_FAIL -gt 0 ] || [ $STG_FAIL -gt 0 ] || [ $MARTS_FAIL -gt 0 ]; then
    python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'PARTIAL')" 2>/dev/null || true
  else
    python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'SUCCESS')" 2>/dev/null || true
  fi

  echo "Batch termine - Prochain run: $(date -d "+${INTERVAL_MIN} minutes" 2>/dev/null || echo "${INTERVAL_MIN}min")"
  sleep $((INTERVAL_MIN * 60))
done
