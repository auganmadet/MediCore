#!/bin/bash
set -euo pipefail

# Timeout par phase (surchargeable via PHASE_TIMEOUT_SEC, defaut 30 min)
PHASE_TIMEOUT_SEC=${PHASE_TIMEOUT_SEC:-1800}
# Timeout ref_reload plus long (defaut 5h car 14 tables ~3h-3h30)
REF_TIMEOUT_SEC=${REF_TIMEOUT_SEC:-18000}

# Graceful shutdown : trap SIGTERM/SIGINT pour que docker stop ne laisse pas de zombies
SHUTDOWN_REQUESTED=0
trap 'echo "Signal recu, arret apres la phase en cours..."; SHUTDOWN_REQUESTED=1' SIGTERM SIGINT

# --- Intervalles et rythmes (surchargeable via variables d'environnement) ---
# CDC : intervalle entre chaque consume Kafka (10 min prod, 2 min dev)
if [ "${ENV}" = "prod" ]; then
  CDC_INTERVAL_MIN=${CDC_INTERVAL_MIN:-10}
else
  CDC_INTERVAL_MIN=${CDC_INTERVAL_MIN:-2}
fi
# dbt : toutes les N iterations CDC (6 = toutes les ~60 min prod, 3 = ~6 min dev)
if [ "${ENV}" = "prod" ]; then
  DBT_EVERY_N=${DBT_EVERY_N:-6}
else
  DBT_EVERY_N=${DBT_EVERY_N:-3}
fi

# --- Mode nuit (WH dort, cycles reduits) ---
NIGHT_START=${NIGHT_START:-21}
NIGHT_END=${NIGHT_END:-7}
# Heure du CDC pre-reload (vider backlog Kafka avant TRUNCATE)
NIGHT_CDC_HOUR=${NIGHT_CDC_HOUR:-00}
NIGHT_CDC_MIN=${NIGHT_CDC_MIN:-30}
# Heure du ref_reload (avance a 01h pour finir avant 05h)
REF_RELOAD_HOUR=${REF_RELOAD_HOUR:-01}
# Heure du cycle dbt post-reload (apres fin ref_reload)
POST_RELOAD_DBT_HOUR=${POST_RELOAD_DBT_HOUR:-04}
POST_RELOAD_DBT_MIN=${POST_RELOAD_DBT_MIN:-30}

LOCK_FILE="/tmp/bulk_load.lock"
REF_DONE_FLAG="/tmp/ref_bulk_done_today"
NIGHT_CDC_DONE_FLAG="/tmp/night_cdc_done"
POST_RELOAD_DBT_DONE_FLAG="/tmp/post_reload_dbt_done"
MB_PROV_DONE_FLAG="/tmp/mb_provision_done_today"

# Alerting Teams (optionnel : si TEAMS_WEBHOOK_URL est vide, les erreurs sont loguees sans alerte)
ALERT_THRESHOLD=${ALERT_THRESHOLD:-3}
KAFKA_LAG_THRESHOLD=${KAFKA_LAG_THRESHOLD:-10000}
REF_FAIL=0; CDC_FAIL=0; STG_FAIL=0; SNAP_FAIL=0; MARTS_FAIL=0; TEST_FAIL=0; MARTS_TEST_FAIL=0; FRESH_FAIL=0; ZERO_VOL=0; LAG_HIGH=0

# Compteur pour declencher dbt toutes les N iterations CDC
DBT_CYCLE_COUNT=0
# Flag : ref_reload termine, forcer un cycle dbt au prochain passage
REF_RELOAD_JUST_DONE=0

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

# --- Fonctions utilitaires ---

# Determine si on est en mode nuit (NIGHT_START <= heure < NIGHT_END, avec wrap minuit)
is_night() {
  local hour
  hour=$(date +%H | sed 's/^0//')
  if [ "$NIGHT_START" -gt "$NIGHT_END" ]; then
    # Wrap minuit : ex 21h-07h -> nuit si heure >= 21 OU heure < 7
    [ "$hour" -ge "$NIGHT_START" ] || [ "$hour" -lt "$NIGHT_END" ]
  else
    [ "$hour" -ge "$NIGHT_START" ] && [ "$hour" -lt "$NIGHT_END" ]
  fi
}

# Phase CDC : consume Kafka -> Snowflake RAW
run_cdc() {
  echo "Phase CDC"
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'cdc_batch')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" python /app/pipelines/daily_cdc_batch.py --run-id "$RUN_ID"; then
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

    # Lag check : alerte si lag > seuil N fois consecutives
    LAG_TOTAL=$(grep '^total=' /tmp/cdc_lag_metrics 2>/dev/null | cut -d= -f2 || echo "0")
    if [ "$LAG_TOTAL" -gt "$KAFKA_LAG_THRESHOLD" ] 2>/dev/null; then
      LAG_HIGH=$((LAG_HIGH + 1))
      echo "CDC lag: $LAG_TOTAL records ($LAG_HIGH consecutive)"
      [ $LAG_HIGH -eq $ALERT_THRESHOLD ] && send_teams_alert "CDC lag ($LAG_TOTAL records)" "$LAG_HIGH"
    else
      [ $LAG_HIGH -ge $ALERT_THRESHOLD ] && send_teams_alert "CDC lag" "$LAG_HIGH" "recovery"
      LAG_HIGH=0
    fi
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'cdc_batch', 'FAILED', error='CDC batch failed')" 2>/dev/null || true
    CDC_FAIL=$((CDC_FAIL + 1))
    echo "CDC failed ($CDC_FAIL consecutive)"
    [ $CDC_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "CDC batch" "$CDC_FAIL"
  fi
}

# Phase dbt complete : staging -> snapshot -> marts -> tests -> freshness
run_dbt() {
  echo "Phase dbt (cycle complet)"
  cd /app/dbt

  # 2a. Staging
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_staging')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" dbt run --select tag:staging --target $ENV --vars "{run_id: '$RUN_ID'}"; then
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

  # 2b. Snapshots SCD2 (prod uniquement — inutile en dev/test)
  if [ "$ENV" = "prod" ]; then
    echo "Phase snapshots"
    python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_snapshot')" 2>/dev/null || true
    if timeout "$PHASE_TIMEOUT_SEC" dbt snapshot --target $ENV --vars "{run_id: '$RUN_ID'}"; then
      python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_snapshot', 'SUCCESS')" 2>/dev/null || true
      [ $SNAP_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt snapshot" "$SNAP_FAIL" "recovery"
      SNAP_FAIL=0
    else
      python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_snapshot', 'FAILED', error='dbt snapshot failed')" 2>/dev/null || true
      SNAP_FAIL=$((SNAP_FAIL + 1))
      echo "dbt snapshot failed ($SNAP_FAIL consecutive)"
      [ $SNAP_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt snapshot" "$SNAP_FAIL"
    fi
  fi

  # 2c. Marts
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_marts')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" dbt run --select tag:marts --target $ENV --vars "{run_id: '$RUN_ID'}"; then
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

  # 2d. Tests staging
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_test')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" dbt test --select stg_* --target $ENV --vars "{run_id: '$RUN_ID'}"; then
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

  # 2e. Tests marts
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'dbt_test_marts')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" dbt test --select tag:marts --target $ENV --vars "{run_id: '$RUN_ID'}"; then
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_test_marts', 'SUCCESS')" 2>/dev/null || true
    [ $MARTS_TEST_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "dbt test marts" "$MARTS_TEST_FAIL" "recovery"
    MARTS_TEST_FAIL=0
  else
    python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'dbt_test_marts', 'FAILED', error='dbt test marts failed')" 2>/dev/null || true
    MARTS_TEST_FAIL=$((MARTS_TEST_FAIL + 1))
    echo "dbt test marts failed ($MARTS_TEST_FAIL consecutive)"
    [ $MARTS_TEST_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "dbt test marts" "$MARTS_TEST_FAIL"
  fi
  send_dbt_run_summary "test-marts"

  # 2f. Source freshness
  echo "Phase freshness"
  python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'freshness')" 2>/dev/null || true
  if timeout "$PHASE_TIMEOUT_SEC" dbt source freshness --target $ENV; then
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
}

# ==========================================================================
# BOUCLE PRINCIPALE
# ==========================================================================

echo "MediCore Batch Loop - CDC ${CDC_INTERVAL_MIN}min, dbt every ${DBT_EVERY_N} cycles - ENV: ${ENV}"
echo "  Mode nuit: ${NIGHT_START}h-${NIGHT_END}h (CDC ${NIGHT_CDC_HOUR}:${NIGHT_CDC_MIN}, ref_reload ${REF_RELOAD_HOUR}h, dbt post-reload ${POST_RELOAD_DBT_HOUR}:${POST_RELOAD_DBT_MIN})"

# En dev : mode single-run (pas de boucle infinie)
if [ "${ENV}" = "dev" ] && [ "${BATCH_LOOP:-true}" = "false" ]; then
  echo "Dev mode: boucle desactivee (BATCH_LOOP=false). Lancer manuellement chaque composant."
  exit 0
fi

while true; do
  # Graceful shutdown : verifier avant de demarrer un nouveau cycle
  if [ "$SHUTDOWN_REQUESTED" -eq 1 ]; then
    echo "Arret propre demande (SIGTERM/SIGINT). Fin du batch loop."
    exit 0
  fi

  HOUR=$(date +%H)
  HHMM=$(date +%H%M)
  echo "$(date) - Debut cycle #${HHMM}"

  # Generer un RUN_ID unique pour cette iteration (lineage operationnel)
  RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
  export RUN_ID
  echo "RUN_ID: $RUN_ID"
  python3 -c "from pipelines.utils.audit import log_run_start; log_run_start('$RUN_ID', '${ENV}')" 2>/dev/null || true

  # Verifier qu'un bulk load n'est pas en cours (stale lock detection)
  if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(awk '{print $1}' "$LOCK_FILE" 2>/dev/null)
    if [ -n "$LOCK_PID" ] && [ -d "/proc/$LOCK_PID" ]; then
      echo "Bulk load en cours (PID $LOCK_PID, lock: $LOCK_FILE) - cycle skippe"
      sleep $((CDC_INTERVAL_MIN * 60))
      continue
    else
      echo "Stale lock detecte (PID $LOCK_PID absent) - suppression de $LOCK_FILE"
      rm -f "$LOCK_FILE"
    fi
  fi

  # Reset flags et compteurs quotidiens a minuit
  if [ "$HOUR" = "00" ]; then
    rm -f "$REF_DONE_FLAG" "$NIGHT_CDC_DONE_FLAG" "$POST_RELOAD_DBT_DONE_FLAG" "$MB_PROV_DONE_FLAG"
    REF_FAIL=0; CDC_FAIL=0; STG_FAIL=0; SNAP_FAIL=0; MARTS_FAIL=0
    TEST_FAIL=0; MARTS_TEST_FAIL=0; FRESH_FAIL=0; ZERO_VOL=0; LAG_HIGH=0
    REF_RELOAD_JUST_DONE=0; DBT_CYCLE_COUNT=0
  fi

  # ==================================================================
  # MODE NUIT (21h - 07h) : cycles reduits pour economiser le WH
  # ==================================================================
  if is_night; then

    # --- 21h00 : dernier cycle complet (declenche par le passage jour->nuit) ---
    # Le dernier cycle dbt de la journee est celui juste avant 21h.
    # Apres 21h, on entre en mode nuit.

    # --- CDC pre-reload (vider backlog Kafka avant ref_reload) ---
    # Utilise >= pour ne pas rater la fenetre avec le sleep 10 min
    if [ "$HOUR" -ge "$NIGHT_CDC_HOUR" ] && [ ! -f "$NIGHT_CDC_DONE_FLAG" ] && [ ! -f "$REF_DONE_FLAG" ]; then
      echo "Mode nuit: CDC pre-reload (vider backlog Kafka)"
      run_cdc
      touch "$NIGHT_CDC_DONE_FLAG"
    fi

    # --- Retention audit : purge donnees > 90 jours (1x/jour a 00h) ---
    if [ "$HOUR" = "00" ] && [ ! -f "/tmp/audit_purge_done_today" ]; then
      echo "Phase audit-purge: retention 90 jours"
      python3 -c "
from pipelines.utils.audit import _get_audit_conn
conn = _get_audit_conn()
cur = conn.cursor()
cur.execute(\"DELETE FROM PIPELINE_RUNS WHERE RUN_START < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.execute(\"DELETE FROM PIPELINE_STEP_RUNS WHERE STEP_START < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.execute(\"DELETE FROM DBT_MODEL_RUNS WHERE CREATED_AT < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.execute(\"DELETE FROM CDC_LAG_METRICS WHERE CREATED_AT < DATEADD('day', -90, CURRENT_TIMESTAMP())\")
cur.close()
conn.close()
print('Audit purge terminee')
" 2>/dev/null || echo "Audit purge failed (non bloquant)"
      touch "/tmp/audit_purge_done_today"
    fi
    [ "$HOUR" = "02" ] && rm -f "/tmp/audit_purge_done_today"

    # --- 00h : backup quotidien Metabase (pg_dump) ---
    if [ "$HOUR" = "00" ] && [ ! -f "/tmp/metabase_backup_done_today" ]; then
      echo "Phase backup-metabase: dump quotidien PostgreSQL"
      if bash /app/scripts/backup_metabase.sh; then
        echo "Backup Metabase termine"
      else
        echo "Backup Metabase echec (non bloquant)"
      fi
      touch "/tmp/metabase_backup_done_today"
    fi
    [ "$HOUR" = "02" ] && rm -f "/tmp/metabase_backup_done_today"

    # --- ref_reload 14 tables reference (~3h-3h30) ---
    # Utilise >= au lieu de == pour ne pas rater la fenetre si le cycle tombe entre deux heures
    if [ "$HOUR" -ge "$REF_RELOAD_HOUR" ] && [ "$HOUR" -lt "$POST_RELOAD_DBT_HOUR" ] && [ ! -f "$REF_DONE_FLAG" ]; then
      echo "Phase ref-reload: 14 tables reference (truncate + bulk load)"
      python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'ref_reload')" 2>/dev/null || true
      if timeout "$REF_TIMEOUT_SEC" python /app/pipelines/bulk_load.py --ref-only --truncate --run-id "$RUN_ID"; then
        python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'SUCCESS')" 2>/dev/null || true
        [ $REF_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL" "recovery"
        REF_FAIL=0
        REF_RELOAD_JUST_DONE=1
        touch "$REF_DONE_FLAG"
      else
        python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'FAILED', error='Ref-reload failed')" 2>/dev/null || true
        REF_FAIL=$((REF_FAIL + 1))
        echo "Ref-reload failed ($REF_FAIL consecutive)"
        [ $REF_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL"
      fi
    fi

    # --- 04h30 : 1 CDC + 1 cycle dbt complet (integre ref_reload) ---
    CURRENT_HHMM=$(date +%H%M)
    POST_RELOAD_HHMM="${POST_RELOAD_DBT_HOUR}${POST_RELOAD_DBT_MIN}"
    if [ "$CURRENT_HHMM" -ge "$POST_RELOAD_HHMM" ] && [ ! -f "$POST_RELOAD_DBT_DONE_FLAG" ]; then
      echo "Mode nuit: cycle post-reload (CDC + dbt complet)"
      run_cdc
      run_dbt
      touch "$POST_RELOAD_DBT_DONE_FLAG"
    fi

    # --- 05h00 : détection et provisionnement nouvelles pharmacies (1x/jour) ---
    # Léger si rien à faire (~2s : 1 SELECT Snowflake + 1 auth Metabase)
    # Provisionne automatiquement : groupe + collection + permissions Metabase
    if ([ "$HOUR" = "05" ] || [ "$HOUR" = "06" ]) && [ ! -f "$MB_PROV_DONE_FLAG" ]; then
      echo "Phase metabase-provision: détection nouvelles pharmacies"
      if timeout "$PHASE_TIMEOUT_SEC" python /app/scripts/metabase_maintenance.py; then
        echo "Metabase provision terminé"
      else
        echo "Metabase provision échec (non bloquant)"
      fi
      touch "$MB_PROV_DONE_FLAG"
    fi
    [ "$HOUR" = "07" ] && rm -f "$MB_PROV_DONE_FLAG"

    # Statut global du run
    if [ $CDC_FAIL -gt 0 ] || [ $STG_FAIL -gt 0 ] || [ $MARTS_FAIL -gt 0 ]; then
      python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'PARTIAL')" 2>/dev/null || true
    else
      python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'SUCCESS')" 2>/dev/null || true
    fi

    # En mode nuit, sleep long (10 min) pour ne pas boucler inutilement
    echo "Mode nuit: prochain check dans 10 min"
    sleep 600
    continue
  fi

  # ==================================================================
  # MODE JOUR (07h - 21h) : CDC rapide + dbt periodique
  # ==================================================================

  # Incrementer le compteur de cycles
  DBT_CYCLE_COUNT=$((DBT_CYCLE_COUNT + 1))

  # CDC tourne a chaque iteration
  run_cdc

  # dbt tourne toutes les N iterations OU si ref_reload vient de finir
  RUN_DBT=0
  if [ $REF_RELOAD_JUST_DONE -eq 1 ]; then
    echo "dbt force: ref_reload termine, integration des nouvelles donnees"
    RUN_DBT=1
    REF_RELOAD_JUST_DONE=0
  elif [ $((DBT_CYCLE_COUNT % DBT_EVERY_N)) -eq 0 ]; then
    # Skip dbt si aucune donnee nouvelle (CDC_COUNT == 0 et pas de ref_reload)
    CDC_COUNT=$(cat /tmp/cdc_last_count 2>/dev/null || echo "0")
    if [ "$CDC_COUNT" = "0" ]; then
      echo "dbt skip: aucune nouvelle donnee CDC (cycle $DBT_CYCLE_COUNT)"
    else
      RUN_DBT=1
    fi
  else
    echo "dbt skip: cycle $DBT_CYCLE_COUNT (prochain dbt dans $((DBT_EVERY_N - (DBT_CYCLE_COUNT % DBT_EVERY_N))) cycles)"
  fi

  if [ $RUN_DBT -eq 1 ]; then
    run_dbt
  fi

  # Statut global du run
  if [ $CDC_FAIL -gt 0 ] || [ $STG_FAIL -gt 0 ] || [ $MARTS_FAIL -gt 0 ]; then
    python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'PARTIAL')" 2>/dev/null || true
  else
    python3 -c "from pipelines.utils.audit import log_run_end; log_run_end('$RUN_ID', 'SUCCESS')" 2>/dev/null || true
  fi

  echo "Cycle termine (CDC #$DBT_CYCLE_COUNT) - Prochain CDC dans ${CDC_INTERVAL_MIN}min"
  sleep $((CDC_INTERVAL_MIN * 60))
done
