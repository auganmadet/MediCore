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
# Toutes les heures sont en UTC. Heure francaise = UTC + 2 (ete) / UTC + 1 (hiver)
# Mode nuit : 21h FR (19h UTC) -> 07h FR (05h UTC)
NIGHT_START=${NIGHT_START:-19}
NIGHT_END=${NIGHT_END:-5}
# CDC pre-reload : 21h30 FR (19h30 UTC) — vider backlog Kafka avant reload
NIGHT_CDC_HOUR=${NIGHT_CDC_HOUR:-19}
NIGHT_CDC_MIN=${NIGHT_CDC_MIN:-30}
# ref_reload : 23h FR (21h UTC) — 14 tables reference (~4h30)
REF_RELOAD_HOUR=${REF_RELOAD_HOUR:-21}
# Fin fenêtre ref_reload (heure à laquelle ref_reload ne peut plus démarrer).
# Utilisé par is_ref_reload_window() pour détecter la fenêtre [REF_RELOAD_HOUR,
# POST_RELOAD_DBT_HOUR). Après 02h UTC, ref_reload de la nuit ne se déclenche plus.
# NB : le dbt post-reload n'utilise plus ces variables, il enchaîne désormais
# immédiatement après la fin du ref_reload (flag REF_DONE_FLAG).
POST_RELOAD_DBT_HOUR=${POST_RELOAD_DBT_HOUR:-02}
POST_RELOAD_DBT_MIN=${POST_RELOAD_DBT_MIN:-00}

LOCK_FILE="/tmp/bulk_load.lock"
REF_DONE_FLAG="/tmp/ref_bulk_done_today"
NIGHT_CDC_DONE_FLAG="/tmp/night_cdc_done"
POST_RELOAD_DBT_DONE_FLAG="/tmp/post_reload_dbt_done"
MB_PROV_DONE_FLAG="/tmp/mb_provision_done_today"
# Dev auto-clone : resynchronise MEDICORE_DEV depuis MEDICORE_PROD une fois
# par nuit (clone zero-copy Snowflake, quelques secondes, cout nul). Opt-in.
DEV_AUTO_CLONE=${DEV_AUTO_CLONE:-false}
DEV_CLONE_ROLE=${DEV_CLONE_ROLE:-ACCOUNTADMIN}
DEV_CLONE_DONE_FLAG="/tmp/dev_clone_done_today"
# Extra bulk_load ad-hoc : declenche par un flag manuel contenant les tables
# a recharger (ex: "FACTURES"). Execute APRES pipeline_maintenance pour ne
# pas entrer en competition warehouse. Une seule fois par activation.
EXTRA_BULK_PENDING_FLAG="/tmp/extra_bulk_pending"
EXTRA_BULK_RUNNING_FLAG="/tmp/extra_bulk_running"
# Pre-night healthcheck : go/no-go pour toutes les phases nuit critiques
PRE_NIGHT_OK_FLAG="/tmp/pre_night_ok"
PRE_NIGHT_DONE_FLAG="/tmp/pre_night_done_today"
# 20h30 FR (18h30 UTC) : appel pre_night_healthcheck --fix
PRE_NIGHT_HOUR=${PRE_NIGHT_HOUR:-18}
PRE_NIGHT_MIN=${PRE_NIGHT_MIN:-30}

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

# Determine si on est dans la fenetre ref_reload (REF_RELOAD_HOUR <= heure < POST_RELOAD_DBT_HOUR, avec wrap minuit)
is_ref_reload_window() {
  local hour
  hour=$(date +%H | sed 's/^0//')
  if [ "$REF_RELOAD_HOUR" -gt "$POST_RELOAD_DBT_HOUR" ]; then
    # Wrap minuit : ex 21h-02h -> fenetre si heure >= 21 OU heure < 2
    [ "$hour" -ge "$REF_RELOAD_HOUR" ] || [ "$hour" -lt "$POST_RELOAD_DBT_HOUR" ]
  else
    [ "$hour" -ge "$REF_RELOAD_HOUR" ] && [ "$hour" -lt "$POST_RELOAD_DBT_HOUR" ]
  fi
}

# Phase pre-night-healthcheck : verif + fix auto avant le mode nuit.
# Appelee a 18h30 UTC (20h30 FR) et en fallback si pre_night_ok absent.
# Cree /tmp/pre_night_ok si tout OK, sinon alerte Teams (geree par le script).
run_pre_night_healthcheck() {
  echo "Phase pre-night-healthcheck"
  local exit_code=0
  timeout 900 python /app/scripts/pre_night_healthcheck.py --fix || exit_code=$?

  if [ $exit_code -eq 0 ]; then
    echo "pre-night-healthcheck: OK (nuit autorisee)"
  elif [ $exit_code -eq 2 ]; then
    echo "pre-night-healthcheck: RESTART CONTENEUR REQUIS (.env corrige)"
    echo "  Action : docker compose up -d medicore-elt-batch"
    # Alerte Teams deja envoyee par le script
  else
    echo "pre-night-healthcheck: FAIL (code=$exit_code) — nuit skippee"
  fi
  touch "$PRE_NIGHT_DONE_FLAG"
}

# Post-check CDC pre-reload (2a) : verif flag + lag Kafka acceptable.
# Non bloquant, alerte warning uniquement.
post_check_cdc_prereload() {
  local status="OK"
  local msg=""
  if [ ! -f "$NIGHT_CDC_DONE_FLAG" ]; then
    status="FAIL"; msg="flag night_cdc_done absent"
  else
    local lag_total
    lag_total=$(grep '^total=' /tmp/cdc_lag_metrics 2>/dev/null | cut -d= -f2 || echo "0")
    if [ "$lag_total" -gt "$KAFKA_LAG_THRESHOLD" ] 2>/dev/null; then
      status="WARN"; msg="lag=$lag_total > seuil $KAFKA_LAG_THRESHOLD"
    else
      msg="lag=$lag_total"
    fi
  fi
  echo "[POST-CHECK CDC pre-reload] $status : $msg"
  if [ "$status" != "OK" ]; then
    send_teams_alert "CDC pre-reload post-check: $msg" 1 "warning"
  fi
}

# Post-check ref_reload (2b) : 14 tables non vides + pas de _BACKUP residuel.
# Bloquant : si KO, skip dbt post-reload.
# Retourne 0 si OK, 1 si KO.
post_check_ref_reload() {
  local status="OK"
  local msg=""
  local output
  output=$(python3 << 'PY_EOF'
import snowflake.connector, os, sys
try:
    conn = snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='RAW',
    )
    cur = conn.cursor()
    ref_tables = [
        'RAW_DAYBYDAY', 'RAW_EAN13', 'RAW_FOURNISSEURS', 'RAW_HISTORY',
        'RAW_LOG', 'RAW_LPPR', 'RAW_MANQHISTORY', 'RAW_MEDIPRIX_FACTURES',
        'RAW_PHARMACIE', 'RAW_PHARMACIES', 'RAW_PHARMACIES_ERREUR',
        'RAW_PRODUITS', 'RAW_PRODUITS_NEGATIFS', 'RAW_STOCKHISTORY',
    ]
    empty = []
    for t in ref_tables:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        if cur.fetchone()[0] == 0:
            empty.append(t)
    cur.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE '%_BACKUP'"
    )
    backups = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    if empty or backups:
        print(f'FAIL:empty={empty} backups={backups}')
        sys.exit(1)
    print('OK')
except Exception as e:
    print(f'ERROR:{str(e)[:80]}')
    sys.exit(2)
PY_EOF
)
  if echo "$output" | grep -q "^OK"; then
    status="OK"; msg="14 tables peuplees, 0 _BACKUP residuel"
  else
    status="FAIL"; msg="$output"
  fi
  echo "[POST-CHECK ref_reload] $status : $msg"
  if [ "$status" != "OK" ]; then
    send_teams_alert "ref_reload post-check: $msg" 1 "critical"
    return 1
  fi
  return 0
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

# Resynchronisation MEDICORE_DEV depuis MEDICORE_PROD via CLONE zero-copy.
# Appelee une fois par nuit si DEV_AUTO_CLONE=true, apres toutes les autres
# phases. Le clone est quasi instantane (metadata seulement) et gratuit en
# compute. Garantit que les sessions dev du lendemain partent sur des
# donnees fraiches sans effort manuel.
run_dev_clone() {
  echo "Phase dev-clone: CREATE OR REPLACE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD"
  if python3 -c "
import os, sys, snowflake.connector
try:
    conn = snowflake.connector.connect(
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        user=os.environ['SNOWFLAKE_USER'],
        password=os.environ['SNOWFLAKE_PASSWORD'],
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        role='${DEV_CLONE_ROLE}',
    )
    cur = conn.cursor()
    cur.execute('CREATE OR REPLACE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD')
    cur.close()
    conn.close()
    print('MEDICORE_DEV resynchronise depuis MEDICORE_PROD')
except Exception as e:
    print(f'Dev clone echec: {e}', file=sys.stderr)
    sys.exit(1)
"; then
    touch "$DEV_CLONE_DONE_FLAG"
    echo "Dev clone termine"
  else
    echo "Dev clone echec (non bloquant)"
    send_teams_alert "dev_auto_clone" "1" "failure" 2>/dev/null || true
  fi
}

# ==========================================================================
# BOUCLE PRINCIPALE
# ==========================================================================

# Garde-fou : verifier que SNOWFLAKE_DATABASE (pipelines Python) et la
# database du target dbt (profiles.yml[ENV]) pointent au meme endroit.
# Sans ca, le CDC/bulk ecrit en PROD pendant que dbt ecrit en DEV (ou vice
# versa), les MARTS se desynchronisent silencieusement (cf. incident 2026-04-24).
check_env_coherence() {
  local dbt_db
  dbt_db=$(python3 -c "
import sys, yaml
with open('/app/dbt/profiles.yml') as f:
    profiles = yaml.safe_load(f)
target = '${ENV}'
outputs = profiles.get('medicore', {}).get('outputs', {})
if target not in outputs:
    print(f'TARGET_NOT_FOUND:{target}', file=sys.stderr)
    sys.exit(2)
print(outputs[target].get('database', 'UNKNOWN'))
" 2>/dev/null) || { echo "[FAIL] Lecture profiles.yml impossible (ENV=${ENV})"; exit 1; }

  local sf_db="${SNOWFLAKE_DATABASE:-UNSET}"
  if [ "$dbt_db" != "$sf_db" ]; then
    echo "================================================================"
    echo "[FAIL] Incoherence database Snowflake detectee :"
    echo "  SNOWFLAKE_DATABASE (pipelines Python) = $sf_db"
    echo "  profiles.yml[${ENV}].database (dbt)   = $dbt_db"
    echo ""
    echo "Les pipelines (CDC, bulk_load) ecrivent RAW dans $sf_db mais"
    echo "dbt lit/ecrit STAGING et MARTS dans $dbt_db. Les MARTS vont se"
    echo "desynchroniser. Corriger soit .env (ENV=), soit profiles.yml,"
    echo "soit .env (SNOWFLAKE_DATABASE=) pour qu'ils pointent au meme."
    echo "================================================================"
    send_teams_alert "check_env_coherence" "1" "failure" 2>/dev/null || true
    exit 1
  fi
  echo "[OK] Coherence database confirmee : ${sf_db} (ENV=${ENV})"
}

check_env_coherence

echo "MediCore Batch Loop - CDC ${CDC_INTERVAL_MIN}min, dbt every ${DBT_EVERY_N} cycles - ENV: ${ENV}"
echo "  Mode nuit: ${NIGHT_START}h-${NIGHT_END}h UTC (CDC ${NIGHT_CDC_HOUR}:${NIGHT_CDC_MIN}, ref_reload ${REF_RELOAD_HOUR}h-${POST_RELOAD_DBT_HOUR}h, dbt+maintenance enchaînent après REF_DONE)"
echo "  Heures FR (UTC+2): nuit 21h-07h, CDC 21h30, ref_reload 23h, dbt+maintenance enchaînent après (~23h40 en mode incremental)"
echo "  Dev auto-clone: DEV_AUTO_CLONE=${DEV_AUTO_CLONE} (role: ${DEV_CLONE_ROLE})"

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

  # Reset flags et compteurs quotidiens au debut du mode nuit (19h UTC = 21h FR)
  if [ "$HOUR" = "19" ] && [ "$(date +%M)" -lt "10" ]; then
    rm -f "$REF_DONE_FLAG" "$NIGHT_CDC_DONE_FLAG" "$POST_RELOAD_DBT_DONE_FLAG" "$MB_PROV_DONE_FLAG" "$DEV_CLONE_DONE_FLAG"
    REF_FAIL=0; CDC_FAIL=0; STG_FAIL=0; SNAP_FAIL=0; MARTS_FAIL=0
    TEST_FAIL=0; MARTS_TEST_FAIL=0; FRESH_FAIL=0; ZERO_VOL=0; LAG_HIGH=0
    REF_RELOAD_JUST_DONE=0; DBT_CYCLE_COUNT=0
  fi

  # Reset du flag pre_night_done en milieu de journee (14h UTC = 16h FR)
  # Permet la re-execution du pre_night_healthcheck le soir suivant.
  if [ "$HOUR" = "14" ] && [ "$(date +%M)" -lt "10" ]; then
    rm -f "$PRE_NIGHT_DONE_FLAG"
  fi

  # --- Pre-night healthcheck a 18h30 UTC (20h30 FR) : 30 min avant mode nuit ---
  # Verifie et corrige l'infra + config avant le ref_reload critique.
  # Si FAIL non fixable, alerte Teams et ne cree PAS /tmp/pre_night_ok
  # (toutes les phases nuit critiques seront skippees).
  if [ "$HOUR" -ge "$PRE_NIGHT_HOUR" ] && [ "$HOUR" -lt "19" ] \
     && [ "$(date +%M)" -ge "$PRE_NIGHT_MIN" ] \
     && [ ! -f "$PRE_NIGHT_DONE_FLAG" ]; then
    run_pre_night_healthcheck
  fi

  # Fallback : si on entre en mode nuit et pre_night_ok absent (ex: restart
  # conteneur en fin de journee qui a vide /tmp), relance le healthcheck.
  if is_night && [ ! -f "$PRE_NIGHT_OK_FLAG" ] && [ ! -f "$PRE_NIGHT_DONE_FLAG" ]; then
    echo "Mode nuit sans pre_night_ok (/tmp vide ?) : relance pre-night-healthcheck"
    run_pre_night_healthcheck
  fi

  # ==================================================================
  # MODE NUIT (21h - 07h) : cycles reduits pour economiser le WH
  # ==================================================================
  if is_night; then

    # --- 21h00 : dernier cycle complet (declenche par le passage jour->nuit) ---
    # Le dernier cycle dbt de la journee est celui juste avant 21h.
    # Apres 21h, on entre en mode nuit.

    # --- CDC pre-reload (vider backlog Kafka avant ref_reload) ---
    # Fenetre NIGHT_CDC_HOUR:NIGHT_CDC_MIN (ex: 19:30 UTC = 21h30 FR).
    # Declenche si on est apres l'heure exacte, ou apres NIGHT_CDC_HOUR + 1.
    # Guard : pre_night_ok obligatoire (infra validee a 18h30)
    MINUTE=$(date +%M | sed 's/^0*//')
    MINUTE=${MINUTE:-0}
    if [ ! -f "$PRE_NIGHT_OK_FLAG" ]; then
      echo "Mode nuit: pre_night_ok absent — phase CDC pre-reload skippee"
    elif { [ "$HOUR" -gt "$NIGHT_CDC_HOUR" ] || { [ "$HOUR" -eq "$NIGHT_CDC_HOUR" ] && [ "$MINUTE" -ge "$NIGHT_CDC_MIN" ]; }; } \
         && [ ! -f "$NIGHT_CDC_DONE_FLAG" ] && [ ! -f "$REF_DONE_FLAG" ]; then
      echo "Mode nuit: CDC pre-reload (vider backlog Kafka) — ${HOUR}:${MINUTE} UTC"
      run_cdc
      touch "$NIGHT_CDC_DONE_FLAG"
      # Post-check 2a (non bloquant)
      post_check_cdc_prereload
    fi

    # --- Retention audit : purge donnees > 90 jours (22h FR = 20h UTC) ---
    if [ "$HOUR" = "20" ] && [ ! -f "/tmp/audit_purge_done_today" ]; then
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
    [ "$HOUR" = "22" ] && rm -f "/tmp/audit_purge_done_today"

    # --- 22h FR (20h UTC) : backup quotidien Metabase (pg_dump) ---
    if [ "$HOUR" = "20" ] && [ ! -f "/tmp/metabase_backup_done_today" ]; then
      echo "Phase backup-metabase: dump quotidien PostgreSQL"
      if bash /app/scripts/backup_metabase.sh; then
        echo "Backup Metabase termine"
      else
        echo "Backup Metabase echec (non bloquant)"
      fi
      touch "/tmp/metabase_backup_done_today"
    fi
    [ "$HOUR" = "22" ] && rm -f "/tmp/metabase_backup_done_today"

    # --- ref_reload 14 tables référence ---
    # Fenêtre [REF_RELOAD_HOUR, POST_RELOAD_DBT_HOUR) avec wrap minuit (ex: 21h-02h)
    # Garde : pre_night_ok obligatoire (infra validée à 18h30)
    #
    # Optimisation L1+L5 (plan docs/plans/2026-04-22_optimisation_cost_snowflake.md) :
    #   Dimanche (DOW=0)     -> SKIP : pharmacies fermées, peu de transactions
    #   Lundi (DOW=1)        -> FULL reload : réconciliation hebdomadaire (DELETEs captés)
    #   Mar-Sam (DOW=2..6)   -> INCREMENTAL 30j sur 4 grosses tables + full sur les 10 autres
    # Gain mensuel : ~-391 EUR (ref_reload 4h48 -> 16 min en moyenne)
    #
    # Configuration :
    #   REF_FULL_DOW         : jour de la semaine pour le full reload (défaut : 1 = lundi)
    #   REF_INCREMENTAL_DAYS : fenêtre glissante (défaut : 30 jours)
    #   REF_SKIP_DOW         : jour(s) skippé(s), liste csv (défaut : "0" = dimanche)
    REF_FULL_DOW=${REF_FULL_DOW:-1}
    REF_INCREMENTAL_DAYS=${REF_INCREMENTAL_DAYS:-30}
    REF_SKIP_DOW=${REF_SKIP_DOW:-0}

    if [ ! -f "$PRE_NIGHT_OK_FLAG" ]; then
      is_ref_reload_window && echo "Mode nuit: pre_night_ok absent — ref-reload skippé"
    elif is_ref_reload_window && [ ! -f "$REF_DONE_FLAG" ]; then
      DOW=$(date +%w)  # 0=dimanche, 1=lundi, ..., 6=samedi

      # Détermine le mode : skip / full / incremental
      REF_MODE="incremental"
      if echo ",$REF_SKIP_DOW," | grep -q ",$DOW,"; then
        REF_MODE="skip"
      elif [ "$DOW" = "$REF_FULL_DOW" ]; then
        REF_MODE="full"
      fi

      if [ "$REF_MODE" = "skip" ]; then
        echo "Phase ref-reload: SKIP (DOW=$DOW, pharmacies fermées)"
        # Flag créé pour ne pas bloquer dbt post-reload le dimanche
        touch "$REF_DONE_FLAG"
        python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'SUCCESS', metadata={'mode': 'skip', 'dow': $DOW})" 2>/dev/null || true
      else
        # Full ou incremental : construire la commande bulk_load adaptée
        if [ "$REF_MODE" = "full" ]; then
          echo "Phase ref-reload: FULL (DOW=$DOW, réconciliation hebdomadaire)"
          BULK_CMD="python /app/pipelines/bulk_load.py --ref-only --truncate --run-id $RUN_ID"
        else
          echo "Phase ref-reload: INCREMENTAL ${REF_INCREMENTAL_DAYS}j (DOW=$DOW, 4 tables sur fenêtre glissante)"
          BULK_CMD="python /app/pipelines/bulk_load.py --ref-only --truncate --incremental-days $REF_INCREMENTAL_DAYS --run-id $RUN_ID"
        fi

        python3 -c "from pipelines.utils.audit import log_step_start; log_step_start('$RUN_ID', 'ref_reload')" 2>/dev/null || true
        if timeout "$REF_TIMEOUT_SEC" $BULK_CMD; then
          python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'SUCCESS', metadata={'mode': '$REF_MODE', 'dow': $DOW})" 2>/dev/null || true
          [ $REF_FAIL -ge $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL" "recovery"
          REF_FAIL=0
          # Post-check 2b (bloquant) : si FAIL, ne crée PAS REF_DONE_FLAG -> dbt skippé
          if post_check_ref_reload; then
            REF_RELOAD_JUST_DONE=1
            touch "$REF_DONE_FLAG"
          else
            echo "Ref-reload post-check FAIL : REF_DONE_FLAG non créé, dbt post-reload sera skippé"
          fi
        else
          python3 -c "from pipelines.utils.audit import log_step_end; log_step_end('$RUN_ID', 'ref_reload', 'FAILED', error='Ref-reload failed (mode=$REF_MODE)')" 2>/dev/null || true
          REF_FAIL=$((REF_FAIL + 1))
          echo "Ref-reload failed mode=$REF_MODE ($REF_FAIL consecutive)"
          [ $REF_FAIL -eq $ALERT_THRESHOLD ] && send_teams_alert "Ref-reload" "$REF_FAIL"
        fi
      fi
    fi

    # --- dbt post-reload : enchaîne immédiatement après ref_reload terminé ---
    # Avec l'incremental merge (L1), ref_reload passe de 4h48 à ~16 min.
    # Ancien comportement : attendait POST_RELOAD_DBT_HOUR=02h UTC (04h FR) =
    # battement de 4h30 inutile. Nouveau : dès que REF_DONE_FLAG présent.
    # Le cycle batch_loop sleep 10 min, donc dbt tourne ~10 min après fin ref_reload.
    if [ -f "$REF_DONE_FLAG" ] && [ ! -f "$POST_RELOAD_DBT_DONE_FLAG" ]; then
      echo "Mode nuit: cycle post-reload (CDC + dbt complet)"
      run_cdc
      run_dbt
      touch "$POST_RELOAD_DBT_DONE_FLAG"
    fi

    # --- pipeline_maintenance : enchaîne immédiatement après dbt post-reload ---
    # 4 phases post-exec : CDC, Bulk, dbt, Metabase (H1-H7 déjà vérifiés en pre-night).
    # --fix-safe : corrections sûres uniquement (pas de reload lourd).
    # Rapport Teams disponible dès le soir (~23h50 FR au lieu de 04h40 FR).
    if [ -f "$REF_DONE_FLAG" ] && [ -f "$POST_RELOAD_DBT_DONE_FLAG" ] && [ ! -f "$MB_PROV_DONE_FLAG" ]; then
      echo "Phase pipeline-maintenance: 4 phases (CDC, bulk, dbt, Metabase)"
      if timeout "$PHASE_TIMEOUT_SEC" python /app/scripts/pipeline_maintenance.py --fix-safe; then
        echo "Pipeline maintenance termine"
      else
        echo "Pipeline maintenance echec (non bloquant)"
      fi
      touch "$MB_PROV_DONE_FLAG"
    fi

    # --- Extra bulk_load ad-hoc (catchup manuel d'une table) ---
    # Usage : docker exec medicore_elt_batch bash -c "echo FACTURES > /tmp/extra_bulk_pending"
    # Declenche apres pipeline_maintenance pour ne pas entrer en competition warehouse.
    # CLONE+SWAP integre par bulk_load.py -> rollback auto si echec.
    # Le pending flag est supprime apres succes pour eviter re-run involontaire.
    if [ -f "$PRE_NIGHT_OK_FLAG" ] \
       && [ -f "$REF_DONE_FLAG" ] \
       && [ -f "$POST_RELOAD_DBT_DONE_FLAG" ] \
       && [ -f "$MB_PROV_DONE_FLAG" ] \
       && [ -f "$EXTRA_BULK_PENDING_FLAG" ] \
       && [ ! -f "$EXTRA_BULK_RUNNING_FLAG" ]; then
      touch "$EXTRA_BULK_RUNNING_FLAG"
      EXTRA_TABLES=$(cat "$EXTRA_BULK_PENDING_FLAG" | tr -d '\n' | tr -s ' ')
      echo "Phase extra-bulk-load: $EXTRA_TABLES (ad-hoc, catchup manuel)"
      # shellcheck disable=SC2086
      if timeout "$REF_TIMEOUT_SEC" python /app/pipelines/bulk_load.py --tables $EXTRA_TABLES --truncate --run-id "extra-$(date +%Y%m%d)"; then
        echo "Extra bulk_load $EXTRA_TABLES: SUCCESS"
        rm -f "$EXTRA_BULK_PENDING_FLAG"
        send_teams_alert "Extra bulk_load $EXTRA_TABLES" 1 "recovery"
      else
        echo "Extra bulk_load $EXTRA_TABLES: FAIL"
        send_teams_alert "Extra bulk_load $EXTRA_TABLES" 1 "failure"
      fi
      rm -f "$EXTRA_BULK_RUNNING_FLAG"
    fi

    # --- Dev auto-clone (opt-in via DEV_AUTO_CLONE=true) ---
    # Resynchronise MEDICORE_DEV depuis MEDICORE_PROD apres toutes les autres
    # phases nocturnes. Clone zero-copy = ~2 secondes, compute gratuit.
    # Executee uniquement en production (ENV=prod) pour eviter de cloner
    # depuis DEV sur lui-meme pendant les sessions de dev.
    if [ "$DEV_AUTO_CLONE" = "true" ] \
       && [ "$ENV" = "prod" ] \
       && [ -f "$MB_PROV_DONE_FLAG" ] \
       && [ ! -f "$DEV_CLONE_DONE_FLAG" ]; then
      run_dev_clone
    fi

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
