"""Pre-night healthcheck : verification + correction avant le mode nuit.

Execute a 20h30 FR (18h30 UTC) par batch_loop.sh, 30 min avant le passage en
mode nuit. Valide que l'infrastructure et la configuration sont pretes pour
la sequence nocturne critique (CDC pre-reload -> ref_reload -> dbt post-reload).

Checks (infrastructure + config, pas d'etat post-execution) :

    N1  Infrastructure H1-H7 (MySQL, Kafka, Snowflake, warehouse, Metabase,
                              Debezium, permissions Snowflake)
    N2  Config Debezium   (topic.prefix, table.include.list, snapshot.mode)
    N3  Config env vars   (REF_RELOAD_HOUR, CDC_KAFKA_TOPIC_PREFIX, NIGHT_*)
    N4  Code fixes presents dans le conteneur (batch_loop.sh + daily_cdc_batch.py)
    N5  Pas de lock stale (/tmp/bulk_load.lock)
    N6  Pas de table _BACKUP residuelle (reliquat d'un CLONE+SWAP avorte)
    N7  Schema CDC uniforme sur les 4 tables RAW (3 colonnes méta)
    N8  Schema drift MySQL / Snowflake (réutilise B6 de bulk_maintenance)

Auto-fix (avec --fix) :

    H2 restart Kafka, H3 reconnexion Snowflake, H4 resume warehouse,
    H6 restart Debezium, N2 POST config Debezium correcte, N5 rm lock stale,
    N6 DROP _BACKUP residuelles.

Non auto-fixables (alerte + exit non-zero) : N3 (edition .env humaine),
N4 (rebuild image), N7 (DDL manuel), N8 (evolution schema MySQL).

Sortie :
    Exit 0 + touch /tmp/pre_night_ok  ->  nuit autorisee
    Exit !=0 + alerte Teams critique  ->  batch_loop skippe la nuit

Usage :
    python scripts/pre_night_healthcheck.py              # check uniquement
    python scripts/pre_night_healthcheck.py --fix        # check + fix automatique
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

from healthcheck_maintenance import (
    check_h1_mysql, check_h2_kafka, check_h3_snowflake, check_h4_warehouse,
    check_h5_metabase, check_h6_debezium, check_h7_permissions,
    fix_h2_kafka, fix_h3_snowflake, fix_h4_warehouse, fix_h6_debezium,
    KAFKA_CONNECT_URL,
)
from bulk_maintenance import check_b6_schema_drift

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PRE_NIGHT_OK_FLAG = '/tmp/pre_night_ok'
PRE_NIGHT_RESTART_REQUIRED_FLAG = '/tmp/pre_night_restart_required'
BULK_LOCK_FILE = '/tmp/bulk_load.lock'
ENV_FILE = '/app/.env'

CDC_TABLES_RAW = ['RAW_COMMANDES', 'RAW_FACTURES', 'RAW_ORDERS', 'RAW_MODSTOCK']
EXPECTED_CDC_COLUMNS = {'CDC_OPERATION', 'CDC_TIMESTAMP', 'CDC_LSN'}

EXPECTED_DEBEZIUM_CONFIG = {
    'topic.prefix': 'winstat_rds',
    'table.include.list': 'winstat.COMMANDES,winstat.FACTURES,winstat.ORDERS,winstat.MODSTOCK',
    'snapshot.mode': 'schema_only',
}

EXPECTED_ENV_VARS = {
    'REF_RELOAD_HOUR': '21',
    'POST_RELOAD_DBT_HOUR': '02',
    'NIGHT_START': '19',
    'NIGHT_END': '5',
    'CDC_KAFKA_TOPIC_PREFIX': 'winstat_rds.winstat',
}

CODE_FIX_PATTERNS = {
    '/app/scripts/batch_loop.sh': [
        ('is_ref_reload_window', 'fix wrap-minuit fenêtres ref_reload'),
    ],
    '/app/pipelines/daily_cdc_batch.py': [
        ('CDC_DECIMAL_COLUMNS', 'mapping DECIMAL paramétré par table'),
        ('_reconnect_main', 'reconnexion auto session Snowflake expiree'),
        ('FALLBACK_MAX_CONSECUTIVE_FAILS', 'circuit-breaker fallback row-by-row'),
    ],
}


def get_snowflake_conn():
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='RAW',
    )


def check_n2_debezium_config() -> Tuple[bool, Any]:
    """N2 : config Debezium conforme aux attentes."""
    try:
        req = urllib.request.Request(f'{KAFKA_CONNECT_URL}/connectors', method='GET')
        connectors = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if not connectors:
            return False, {'error': 'aucun connector'}
        name = connectors[0]
        req = urllib.request.Request(f'{KAFKA_CONNECT_URL}/connectors/{name}/config', method='GET')
        config = json.loads(urllib.request.urlopen(req, timeout=10).read())

        drift = {}
        for key, expected in EXPECTED_DEBEZIUM_CONFIG.items():
            actual = config.get(key, '')
            if actual != expected:
                drift[key] = {'expected': expected, 'actual': actual}
        return len(drift) == 0, {'connector': name, 'drift': drift}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def _parse_env_file(env_path: str) -> Dict[str, str]:
    """Parse un .env simple (VAR=value par ligne, # pour commentaires).

    Returns :
        Dict des vars definies. Vars commentees ou absentes non incluses.
    """
    vars_found: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return vars_found
    for line in Path(env_path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        vars_found[key.strip()] = value.strip()
    return vars_found


def check_n3_env_vars() -> Tuple[bool, Any]:
    """N3 : variables d'environnement critiques conformes dans .env.

    Lit le fichier .env (pas os.getenv qui reflete l'etat RAM du process).
    Ceci permet de détecter un drift appliqué mais non encore répercuté
    par un restart du conteneur.

    FAIL uniquement si la var est DEFINIE dans .env ET DIFFERENTE de l'attendu.
    Si la var n'est pas dans .env, batch_loop.sh utilise son default interne.
    """
    env_vars = _parse_env_file(ENV_FILE)
    drift = {}
    for var, expected in EXPECTED_ENV_VARS.items():
        actual = env_vars.get(var)
        if actual is not None and actual != expected:
            drift[var] = {'expected': expected, 'actual': actual}
    return len(drift) == 0, {'drift': drift}


def check_n4_code_fixes() -> Tuple[bool, Any]:
    """N4 : code fixes critiques presents dans le conteneur."""
    missing = {}
    for file_path, patterns in CODE_FIX_PATTERNS.items():
        if not os.path.exists(file_path):
            missing[file_path] = 'fichier absent'
            continue
        try:
            content = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            missing[file_path] = f'lecture impossible: {str(e)[:50]}'
            continue
        missing_patterns = [desc for pat, desc in patterns if pat not in content]
        if missing_patterns:
            missing[file_path] = missing_patterns
    return len(missing) == 0, {'missing': missing}


def check_n5_stale_lock() -> Tuple[bool, Any]:
    """N5 : pas de lock file periime."""
    if not os.path.exists(BULK_LOCK_FILE):
        return True, {'status': 'aucun lock'}
    try:
        pid = Path(BULK_LOCK_FILE).read_text().strip().split()[0]
        if pid and os.path.exists(f'/proc/{pid}'):
            return False, {'status': 'lock actif', 'pid': pid, 'auto_fix': False}
        return False, {'status': 'lock perime', 'pid': pid, 'auto_fix': True}
    except Exception as e:
        return False, {'status': 'lock illisible', 'error': str(e)[:80], 'auto_fix': True}


def check_n6_residual_backup() -> Tuple[bool, Any]:
    """N6 : pas de table _BACKUP residuelle (reliquat CLONE+SWAP avorte)."""
    try:
        conn = get_snowflake_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE '%_BACKUP'"
        )
        backups = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return len(backups) == 0, {'backups': backups}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_n7_cdc_schema_uniform() -> Tuple[bool, Any]:
    """N7 : schema CDC uniforme (3 colonnes méta sur 4 tables RAW CDC)."""
    try:
        conn = get_snowflake_conn()
        cur = conn.cursor()
        drift = {}
        for table in CDC_TABLES_RAW:
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME='{table}' "
                "AND COLUMN_NAME LIKE 'CDC_%'"
            )
            cdc_cols = {row[0].upper() for row in cur.fetchall()}
            if cdc_cols != EXPECTED_CDC_COLUMNS:
                drift[table] = {
                    'expected': sorted(EXPECTED_CDC_COLUMNS),
                    'actual': sorted(cdc_cols),
                }
        cur.close()
        conn.close()
        return len(drift) == 0, {'drift': drift}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_n8_schema_drift() -> Tuple[bool, Any]:
    """N8 : schema drift MySQL/Snowflake (réutilise B6 bulk_maintenance)."""
    return check_b6_schema_drift()


def fix_n2_debezium_config(drift_info: Dict[str, Any]) -> Tuple[bool, str]:
    """Re-deploie la config Debezium conforme."""
    try:
        name = drift_info.get('connector') or 'winstat-mysql-connector'
        config = {
            'connector.class': 'io.debezium.connector.mysql.MySqlConnector',
            'database.hostname': os.getenv('MYSQL_HOST', 'mysql_cdc'),
            'database.port': os.getenv('MYSQL_PORT', '3306'),
            'database.user': os.getenv('MYSQL_USER'),
            'database.password': os.getenv('MYSQL_PASSWORD'),
            'database.server.id': '184054',
            'database.include.list': 'winstat',
            'table.include.list': EXPECTED_DEBEZIUM_CONFIG['table.include.list'],
            'topic.prefix': EXPECTED_DEBEZIUM_CONFIG['topic.prefix'],
            'snapshot.mode': EXPECTED_DEBEZIUM_CONFIG['snapshot.mode'],
            'snapshot.locking.mode': 'minimal',
            'schema.history.internal.kafka.bootstrap.servers': 'kafka:29092',
            'schema.history.internal.kafka.topic': 'winstat_schema_history',
            'schema.history.internal.store.only.captured.tables.ddl': 'true',
            'tasks.max': '1',
        }
        req = urllib.request.Request(
            f'{KAFKA_CONNECT_URL}/connectors/{name}/config',
            data=json.dumps(config).encode(),
            headers={'Content-Type': 'application/json'},
            method='PUT',
        )
        urllib.request.urlopen(req, timeout=30)
        return True, f'config {name} mise a jour'
    except Exception as e:
        return False, str(e)[:100]


def fix_n7_schema_cdc_uniform(drift_info: Dict[str, Any]) -> Tuple[bool, str]:
    """Corrige N7 : DROP les colonnes CDC obsoletes dans les 4 tables RAW CDC.

    Auto-fixe uniquement le cas 'colonnes en trop' (ex: CDC_SCHEMA, CDC_TABLE
    supprimés du code Python). DROP COLUMN est safe car ces colonnes méta
    sont derivables du contexte (nom de table, etc.).

    Le cas 'colonnes manquantes' (rare) reste en alerte humaine car :
    - Type ambigu (VARCHAR de quelle taille ? NUMBER de quelle precision ?)
    - Risque : ajouter une colonne NULL peut casser une contrainte NOT NULL
      ou un MERGE qui attend la colonne dans l'INSERT.
    """
    drift = drift_info.get('drift', {})
    if not drift:
        return True, 'pas de drift'

    try:
        conn = get_snowflake_conn()
        cur = conn.cursor()
        dropped: List[str] = []
        alerts: List[str] = []

        for table, diff in drift.items():
            actual = set(diff.get('actual', []))
            expected = set(diff.get('expected', EXPECTED_CDC_COLUMNS))
            extra = actual - expected
            missing = expected - actual

            if missing:
                alerts.append(f'{table}: {len(missing)} col manquantes {sorted(missing)} (ajout non-auto)')

            for col in sorted(extra):
                try:
                    cur.execute(f'ALTER TABLE RAW.{table} DROP COLUMN IF EXISTS "{col}"')
                    dropped.append(f'{table}.{col}')
                except Exception as e:
                    alerts.append(f'{table}.{col}: DROP echec ({str(e)[:60]})')

        cur.close()
        conn.close()

        ok = (len(dropped) > 0 or len(drift) == 0) and not alerts
        msg = f'{len(dropped)} col(s) droppee(s): {dropped}'
        if alerts:
            msg += f' | {len(alerts)} alerte(s): {alerts}'
        return ok, msg
    except Exception as e:
        return False, str(e)[:100]


def fix_n3_env_drift(drift_info: Dict[str, Any]) -> Tuple[bool, str]:
    """Corrige N3 : reecrit .env avec les valeurs attendues.

    Edite le fichier .env (monte en volume dans le conteneur). Pour chaque var
    en drift, remplace la ligne existante ou ajoutée la ligne si absente.

    IMPORTANT : docker-compose ne relit pas .env sans restart du conteneur.
    Cette fonction crée /tmp/pre_night_restart_required pour signaler a
    batch_loop.sh qu'un restart humain est necessaire avant la nuit.
    """
    import re
    drift = drift_info.get('drift', {})
    if not drift:
        return True, 'pas de drift'
    if not os.path.exists(ENV_FILE):
        return False, f'{ENV_FILE} introuvable (volume non monte ?)'

    try:
        content = Path(ENV_FILE).read_text(encoding='utf-8')
        updated_vars: List[str] = []

        for var, diff in drift.items():
            expected = diff['expected']
            pattern = rf'^{re.escape(var)}=.*$'
            replacement = f'{var}={expected}'
            new_content, nb_subs = re.subn(pattern, replacement, content,
                                           flags=re.MULTILINE)
            if nb_subs > 0:
                content = new_content
                updated_vars.append(f'{var}={expected} (remplace)')
            else:
                content = content.rstrip('\n') + f'\n{replacement}\n'
                updated_vars.append(f'{var}={expected} (ajoutée)')

        Path(ENV_FILE).write_text(content, encoding='utf-8')
        Path(PRE_NIGHT_RESTART_REQUIRED_FLAG).touch()
        return True, (f'{len(updated_vars)} var(s) corrigees: {updated_vars} '
                      '— RESTART CONTENEUR REQUIS')
    except Exception as e:
        return False, str(e)[:100]


def fix_n5_stale_lock() -> Tuple[bool, str]:
    """Supprime un lock file perime (PID mort)."""
    try:
        os.remove(BULK_LOCK_FILE)
        return True, f'{BULK_LOCK_FILE} supprimés'
    except Exception as e:
        return False, str(e)[:100]


def _mysql_type_to_snowflake(mysql_column_type: str) -> str:
    """Convertit MySQL COLUMN_TYPE en type Snowflake.

    Cas courants (95% du schema) : int, bigint, smallint, tinyint, decimal(M,D),
    varchar(N), char(N), text, date, datetime, timestamp, float, double.

    Returns :
        Type Snowflake (ex: 'NUMBER(8,2)', 'VARCHAR(40)', 'TIMESTAMP_NTZ').
    """
    import re
    t = mysql_column_type.lower().strip()
    # decimal(M,D), numeric(M,D)
    m = re.match(r'^(decimal|numeric)\((\d+),(\d+)\)', t)
    if m:
        return f'NUMBER({m.group(2)},{m.group(3)})'
    # varchar(N), char(N)
    m = re.match(r'^(var)?char\((\d+)\)', t)
    if m:
        return f'VARCHAR({m.group(2)})'
    # int(N), bigint(N), smallint(N), tinyint(N), mediumint(N)
    if t.startswith(('bigint', 'int', 'smallint', 'tinyint', 'mediumint')):
        if t.startswith('bigint'):
            return 'BIGINT'
        if t.startswith('smallint') or t.startswith('tinyint'):
            return 'SMALLINT'
        return 'INTEGER'
    # text variants
    if 'text' in t:
        return 'VARCHAR'
    # date/time
    if t == 'date':
        return 'DATE'
    if t in ('datetime', 'timestamp') or t.startswith(('datetime', 'timestamp')):
        return 'TIMESTAMP_NTZ'
    if t == 'time':
        return 'TIME'
    # float/double
    if t.startswith(('float', 'double')):
        return 'FLOAT'
    # boolean
    if t in ('boolean', 'bool', 'bit(1)'):
        return 'BOOLEAN'
    # fallback : VARCHAR pour les types inconnus (sur, evite une erreur DDL)
    return 'VARCHAR'


def fix_n8_schema_drift(drift_info: Dict[str, Any]) -> Tuple[bool, str]:
    """Corrige N8 : ajoutée les colonnes MySQL manquantes en Snowflake.

    Auto-fixe uniquement le cas 'missing_in_snowflake' (colonne ajoutée en MySQL).
    Les cas 'extra_in_snowflake' (colonne supprimée en MySQL) restent en alerte
    humaine car DROP perdrait l'historique.
    """
    import mysql.connector
    drift = drift_info.get('drift', {})
    if not drift:
        return True, 'pas de drift'

    added: List[str] = []
    alerts: List[str] = []
    try:
        my_conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'winstat'),
            connection_timeout=10,
        )
        my_cur = my_conn.cursor()
        sf_conn = get_snowflake_conn()
        sf_cur = sf_conn.cursor()

        for mysql_table, info in drift.items():
            missing = info.get('missing_in_snowflake', [])
            extra = info.get('extra_in_snowflake', [])

            if extra:
                alerts.append(f'{mysql_table}: {len(extra)} col supprimée MySQL (DROP non-auto)')

            if not missing:
                continue

            # Recupere le type MySQL pour chaque colonne manquante
            placeholders = ','.join(['%s'] * len(missing))
            my_cur.execute(
                f'SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.columns '
                f"WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                f'AND UPPER(COLUMN_NAME) IN ({placeholders})',
                [os.getenv('MYSQL_DATABASE', 'winstat'), mysql_table]
                + [c.upper() for c in missing],
            )
            col_types = {row[0].upper(): row[1] for row in my_cur.fetchall()}

            sf_table = f'RAW_{mysql_table}'
            for col in missing:
                mysql_type = col_types.get(col.upper())
                if not mysql_type:
                    alerts.append(f'{sf_table}.{col}: type MySQL introuvable')
                    continue
                sf_type = _mysql_type_to_snowflake(mysql_type)
                try:
                    sf_cur.execute(f'ALTER TABLE RAW.{sf_table} ADD COLUMN "{col.upper()}" {sf_type}')
                    added.append(f'{sf_table}.{col} ({mysql_type} -> {sf_type})')
                except Exception as e:
                    alerts.append(f'{sf_table}.{col}: ALTER echoue ({str(e)[:60]})')

        my_cur.close(); my_conn.close()
        sf_cur.close(); sf_conn.close()

        ok = len(added) > 0 and not alerts
        msg = f'{len(added)} ajout(s): {added}'
        if alerts:
            msg += f' | {len(alerts)} alerte(s): {alerts}'
        return ok, msg
    except Exception as e:
        return False, str(e)[:100]


def fix_n6_residual_backup(backups: List[str]) -> Tuple[bool, str]:
    """DROP les tables _BACKUP residuelles."""
    try:
        conn = get_snowflake_conn()
        cur = conn.cursor()
        dropped = []
        for table in backups:
            cur.execute(f'DROP TABLE IF EXISTS RAW.{table}')
            dropped.append(table)
        cur.close()
        conn.close()
        return True, f'{len(dropped)} table(s) _BACKUP droppee(s): {dropped}'
    except Exception as e:
        return False, str(e)[:100]


def send_teams_alert(failures: Dict[str, Any]) -> None:
    """Alerte Teams si echec critique non recuperable."""
    webhook = os.getenv('TEAMS_WEBHOOK_URL')
    if not webhook:
        return
    lines = [f'- **{code}** : {info}' for code, info in failures.items()]
    body = 'Pre-night healthcheck KO. Nuit SKIPPEE.\n\n' + '\n'.join(lines)
    payload = {
        'type': 'message',
        'attachments': [{
            'contentType': 'application/vnd.microsoft.card.adaptive',
            'content': {
                'type': 'AdaptiveCard',
                'version': '1.2',
                'body': [
                    {'type': 'TextBlock', 'text': 'ALERTE MediCore : pre-night healthcheck FAIL',
                     'weight': 'Bolder', 'color': 'Attention', 'size': 'Medium'},
                    {'type': 'TextBlock', 'text': body, 'wrap': True},
                ],
            },
        }],
    }
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        logger.warning(f'Teams alert echec: {e}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Pre-night healthcheck (N1-N8)')
    parser.add_argument('--fix', action='store_true',
                        help='Correction automatique des problemes fixables')
    args = parser.parse_args()

    print('=' * 70)
    print('  PRE-NIGHT HEALTHCHECK')
    print('=' * 70)

    # Nettoyage prealable : supprimer les flags s'ils existent (seront recrees si OK)
    for f in (PRE_NIGHT_OK_FLAG, PRE_NIGHT_RESTART_REQUIRED_FLAG):
        if os.path.exists(f):
            os.remove(f)

    # Bloc 1 : infrastructure H1-H7 (réutilise healthcheck_maintenance)
    print('\n--- N1 Infrastructure (H1-H7) ---')
    h_checks = [
        ('H1', 'MySQL RDS', check_h1_mysql, None),
        ('H2', 'Kafka broker', check_h2_kafka, fix_h2_kafka),
        ('H3', 'Snowflake', check_h3_snowflake, fix_h3_snowflake),
        ('H4', 'Warehouse actif', check_h4_warehouse, fix_h4_warehouse),
        ('H5', 'Metabase API', check_h5_metabase, None),
        ('H6', 'Debezium connector', check_h6_debezium, fix_h6_debezium),
        ('H7', 'Permissions Snowflake', check_h7_permissions, None),
    ]
    h_results: Dict[str, Dict[str, Any]] = {}
    for code, name, check_fn, fix_fn in h_checks:
        ok, msg = check_fn()
        h_results[code] = {'ok': ok, 'msg': msg, 'fix_fn': fix_fn}
        print(f'  {code} {name:.<35} {"OK" if ok else "FAIL"} ({msg})')

    # Bloc 2 : checks config / etat specifiques pre-night
    print('\n--- N2-N8 Config et etat ---')
    n_checks = [
        ('N2', 'Config Debezium', check_n2_debezium_config,
         lambda info: fix_n2_debezium_config(info)),
        ('N3', 'Env vars critiques', check_n3_env_vars,
         lambda info: fix_n3_env_drift(info)),
        ('N4', 'Code fixes presents', check_n4_code_fixes, None),
        ('N5', 'Lock file non stale', check_n5_stale_lock,
         lambda info: fix_n5_stale_lock() if info.get('auto_fix') else (False, 'non auto-fixable')),
        ('N6', 'Pas de _BACKUP residuel', check_n6_residual_backup,
         lambda info: fix_n6_residual_backup(info.get('backups', []))),
        ('N7', 'Schema CDC uniforme', check_n7_cdc_schema_uniform,
         lambda info: fix_n7_schema_cdc_uniform(info)),
        ('N8', 'Schema drift MySQL/SF', check_n8_schema_drift,
         lambda info: fix_n8_schema_drift(info)),
    ]
    n_results: Dict[str, Dict[str, Any]] = {}
    for code, name, check_fn, fix_fn in n_checks:
        ok, info = check_fn()
        n_results[code] = {'ok': ok, 'info': info, 'fix_fn': fix_fn}
        summary = info if isinstance(info, str) else json.dumps(info, default=str)[:120]
        print(f'  {code} {name:.<35} {"OK" if ok else "FAIL"} {summary}')

    # Corrections automatiques
    if args.fix:
        print('\n--- Corrections automatiques ---')

        # H2, H3, H4, H6 (reutilisent healthcheck_maintenance avec garde-fous)
        for code, result in h_results.items():
            if not result['ok'] and result['fix_fn']:
                fix_ok, fix_msg = result['fix_fn']()
                print(f'  {code} fix: {"OK" if fix_ok else "FAIL"} ({fix_msg})')
                if fix_ok:
                    # Re-check
                    _, name, check_fn, _ = next(c for c in h_checks if c[0] == code)
                    ok, msg = check_fn()
                    h_results[code] = {'ok': ok, 'msg': msg, 'fix_fn': result['fix_fn']}
                    print(f'  {code} re-check: {"OK" if ok else "FAIL"} ({msg})')

        # N2, N5, N6 (fixables)
        for code, result in n_results.items():
            if not result['ok'] and result['fix_fn']:
                fix_ok, fix_msg = result['fix_fn'](result['info'])
                print(f'  {code} fix: {"OK" if fix_ok else "FAIL"} ({fix_msg})')
                if fix_ok:
                    _, name, check_fn, _ = next(c for c in n_checks if c[0] == code)
                    ok, info = check_fn()
                    n_results[code] = {'ok': ok, 'info': info, 'fix_fn': result['fix_fn']}
                    summary = info if isinstance(info, str) else json.dumps(info, default=str)[:120]
                    print(f'  {code} re-check: {"OK" if ok else "FAIL"} {summary}')

    # Synthese finale
    all_results = {**{k: v['ok'] for k, v in h_results.items()},
                   **{k: v['ok'] for k, v in n_results.items()}}
    nb_fail = sum(1 for ok in all_results.values() if not ok)

    print('\n' + '=' * 70)
    print(f'  Synthese : {len(all_results) - nb_fail}/{len(all_results)} OK, {nb_fail} FAIL')
    print('=' * 70)

    # Cas particulier : fix N3 appliqué mais restart conteneur requis
    # Ne pas creer pre_night_ok meme si tout est OK en apparence : les env vars
    # du process en cours ont encore les anciennes valeurs.
    if os.path.exists(PRE_NIGHT_RESTART_REQUIRED_FLAG):
        print(f'\n  Flag {PRE_NIGHT_RESTART_REQUIRED_FLAG} present.')
        print('  .env corrigée mais le conteneur a encore les anciennes valeurs en RAM.')
        print('  ACTION HUMAINE REQUISE : docker compose up -d medicore-elt-batch')
        send_teams_alert({'N3': '.env corrigée, restart medicore_elt_batch requis'})
        print('  Nuit SKIPPEE. Alerte Teams envoyee.')
        return 2

    if nb_fail == 0:
        Path(PRE_NIGHT_OK_FLAG).touch()
        print(f'\n  Nuit autorisee : {PRE_NIGHT_OK_FLAG} crée')
        return 0

    # Fails residuels : alerte Teams + pas de flag
    failures = {code: (h_results[code].get('msg') if code in h_results
                       else n_results[code].get('info'))
                for code, ok in all_results.items() if not ok}
    send_teams_alert(failures)
    print('\n  Nuit SKIPPEE. Alerte Teams envoyee si webhook configure.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
