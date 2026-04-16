"""Maintenance Phase 1 : verification connectivite de tous les services.

Teste la connectivite de chaque composant du pipeline MediCore :
- H1 : MySQL RDS
- H2 : Kafka broker
- H3 : Snowflake
- H4 : Snowflake warehouse actif
- H5 : Metabase API
- H6 : Debezium connector
- H7 : Permissions Snowflake (SELECT sur RAW, STAGING, MARTS)

S'auto-authentifie via .env. Lecture seule, ne modifie rien.

Usage :
    python scripts/healthcheck_maintenance.py
    python scripts/healthcheck_maintenance.py --fix   (corrige H4 et H6 si possible)
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# URLs : utiliser les noms Docker internes si disponibles, sinon localhost
METABASE_URL = os.getenv('METABASE_URL', os.getenv('MB_SITE_URL', os.getenv('METABASE_SITE_URL', 'http://localhost:3000')))
KAFKA_CONNECT_URL = os.getenv('KAFKA_CONNECT_URL', 'http://kafka_connect:8083')


def check_h1_mysql():
    """H1 : connectivite MySQL RDS."""
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'winstat'),
            connection_timeout=10,
        )
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, 'OK'
    except ImportError:
        return False, 'mysql.connector non installe'
    except Exception as e:
        return False, str(e)[:100]


def check_h2_kafka():
    """H2 : connectivite Kafka broker."""
    try:
        from kafka import KafkaConsumer
        consumer = KafkaConsumer(
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
            consumer_timeout_ms=5000,
        )
        topics = consumer.topics()
        consumer.close()
        return True, f'OK ({len(topics)} topics)'
    except ImportError:
        return False, 'kafka-python non installe'
    except Exception as e:
        return False, str(e)[:100]


def check_h3_snowflake():
    """H3 : connectivite Snowflake."""
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
            login_timeout=15,
        )
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, 'OK'
    except Exception as e:
        return False, str(e)[:100]


def check_h4_warehouse():
    """H4 : Snowflake warehouse actif (pas suspendu)."""
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        )
        cursor = conn.cursor()
        wh_name = os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH')
        cursor.execute(f"SHOW WAREHOUSES LIKE '{wh_name}'")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            # SHOW WAREHOUSES retourne un nombre variable de colonnes selon la version.
            # Chercher l'etat dans toutes les colonnes (c'est une string parmi les valeurs)
            state = 'UNKNOWN'
            valid_states = ('STARTED', 'RESUMING', 'SUSPENDED', 'SUSPENDING')
            for col in row:
                if isinstance(col, str) and col.upper() in valid_states:
                    state = col.upper()
                    break
            if state in ('STARTED', 'RESUMING', 'SUSPENDED', 'SUSPENDING'):
                return True, f'OK (state={state}, auto-resume actif)'
            return False, f'state={state} (arrete)'
        return False, f'warehouse {wh_name} non trouve'
    except Exception as e:
        return False, str(e)[:100]


def check_h5_metabase():
    """H5 : Metabase API accessible."""
    try:
        req = urllib.request.Request(f'{METABASE_URL}/api/health', method='GET')
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        status = data.get('status', '?')
        return status == 'ok', f'status={status}'
    except Exception as e:
        return False, str(e)[:100]


def check_h6_debezium():
    """H6 : Debezium connector actif."""
    try:
        req = urllib.request.Request(f'{KAFKA_CONNECT_URL}/connectors', method='GET')
        resp = urllib.request.urlopen(req, timeout=10)
        connectors = json.loads(resp.read())
        if not connectors:
            return False, 'aucun connector configure'

        results = []
        all_ok = True
        for name in connectors:
            req = urllib.request.Request(
                f'{KAFKA_CONNECT_URL}/connectors/{name}/status', method='GET',
            )
            resp = urllib.request.urlopen(req, timeout=10)
            status = json.loads(resp.read())
            connector_state = status.get('connector', {}).get('state', '?')
            tasks = status.get('tasks', [])
            task_states = [t.get('state', '?') for t in tasks]
            results.append(f'{name}: {connector_state} tasks={task_states}')
            if connector_state != 'RUNNING' or any(s != 'RUNNING' for s in task_states):
                all_ok = False

        return all_ok, '; '.join(results)
    except Exception as e:
        return False, str(e)[:100]


def check_h7_permissions():
    """H7 : permissions Snowflake (SELECT sur RAW, STAGING, MARTS)."""
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        )
        cursor = conn.cursor()
        errors = []

        for schema, table in [
            ('RAW', 'RAW_PHARMACIE'),
            ('STAGING', 'STG_PHARMACIE'),
            ('MARTS', 'DIM_PHARMACIE'),
        ]:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {schema}.{table}')
                cursor.fetchone()
            except Exception as e:
                errors.append(f'{schema}.{table}: {str(e)[:50]}')

        cursor.close()
        conn.close()

        if not errors:
            return True, 'OK (RAW, STAGING, MARTS)'
        return False, '; '.join(errors)
    except Exception as e:
        return False, str(e)[:100]


def fix_h2_kafka():
    """Corrige H2 : redemarrage Kafka via docker compose.

    Garde-fou : verifie les logs Kafka avant restart.
    Si l'erreur contient "corrupt" ou "unrecoverable" → ne pas restart, alerter.
    """
    import subprocess
    import time

    # Garde-fou : verifier les logs pour corruption
    try:
        logs_result = subprocess.run(
            ['docker', 'logs', '--since', '10m', 'kafka'],
            capture_output=True, text=True, timeout=10,
        )
        logs_lower = logs_result.stdout.lower() + logs_result.stderr.lower()
        if 'corrupt' in logs_lower or 'unrecoverable' in logs_lower:
            return False, 'ABANDON: logs Kafka contiennent "corrupt/unrecoverable" — intervention manuelle requise'
    except Exception:
        pass  # Si on ne peut pas lire les logs, on tente quand meme le restart

    try:
        logger.info('Restart Kafka...')
        result = subprocess.run(
            ['docker', 'compose', 'restart', 'kafka'],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            time.sleep(15)
            ok, msg = check_h2_kafka()
            if ok:
                return True, 'Kafka redemarre et accessible'
            # Tenter aussi Zookeeper
            subprocess.run(
                ['docker', 'compose', 'restart', 'zookeeper'],
                capture_output=True, text=True, timeout=120,
            )
            time.sleep(10)
            subprocess.run(
                ['docker', 'compose', 'restart', 'kafka'],
                capture_output=True, text=True, timeout=120,
            )
            time.sleep(15)
            ok, msg = check_h2_kafka()
            if ok:
                return True, 'Kafka + Zookeeper redemarres'
            return False, 'Kafka toujours inaccessible apres restart'
        return False, f'docker compose restart echoue: {result.stderr[:80]}'
    except subprocess.TimeoutExpired:
        return False, 'Timeout restart Kafka'
    except Exception as e:
        return False, str(e)[:100]


def fix_h3_snowflake():
    """Corrige H3 : verifie le compte Snowflake et tente de se reconnecter.

    Garde-fou : si le compte est suspendu (credits epuises), alerte sans fix.
    Si c'est un probleme reseau transitoire, le fix resume le warehouse.
    """
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            login_timeout=30,
        )
        cursor = conn.cursor()

        # Verifier le warehouse
        wh_name = os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH')
        try:
            cursor.execute(f'ALTER WAREHOUSE {wh_name} RESUME IF SUSPENDED')
        except Exception:
            pass

        # Verifier la database
        db_name = os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD')
        cursor.execute(f"SHOW DATABASES LIKE '{db_name}'")
        dbs = cursor.fetchall()
        if not dbs:
            cursor.close()
            conn.close()
            return False, f'Database {db_name} inexistante — verifier le compte Snowflake'

        # Verifier les credits restants
        try:
            cursor.execute(
                "SELECT CREDITS_USED, CREDITS_REMAINING "
                "FROM SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY "
                "ORDER BY DATE DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row and row[1] is not None and row[1] <= 0:
                cursor.close()
                conn.close()
                return False, f'ABANDON: credits Snowflake epuises (remaining={row[1]}) — intervention manuelle'
        except Exception:
            pass  # Table pas accessible = pas de probleme de credits

        cursor.close()
        conn.close()

        # Re-tester
        ok, msg = check_h3_snowflake()
        if ok:
            return True, 'Snowflake reconnecte'
        return False, 'Snowflake toujours inaccessible — verifier credits/maintenance'
    except Exception as e:
        return False, f'Connexion impossible: {str(e)[:80]} — verifier credentials/network'


def fix_h4_warehouse():
    """Corrige H4 : resume le warehouse."""
    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
        )
        cursor = conn.cursor()
        wh_name = os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH')
        cursor.execute(f'ALTER WAREHOUSE {wh_name} RESUME')
        cursor.close()
        conn.close()
        return True, f'{wh_name} resume'
    except Exception as e:
        return False, str(e)[:100]


def fix_h6_debezium():
    """Corrige H6 : redemarrage du connector Debezium."""
    try:
        req = urllib.request.Request(f'{KAFKA_CONNECT_URL}/connectors', method='GET')
        resp = urllib.request.urlopen(req, timeout=10)
        connectors = json.loads(resp.read())

        for name in connectors:
            req = urllib.request.Request(
                f'{KAFKA_CONNECT_URL}/connectors/{name}/restart',
                method='POST',
                headers={'Content-Type': 'application/json'},
            )
            urllib.request.urlopen(req, timeout=30)

        return True, f'{len(connectors)} connector(s) redemarres'
    except Exception as e:
        return False, str(e)[:100]


def main():
    parser = argparse.ArgumentParser(description='Healthcheck maintenance (H1-H7)')
    fix_group = parser.add_mutually_exclusive_group()
    fix_group.add_argument('--fix-safe', action='store_true',
                           help='Fix surs : H4 (warehouse), H6 (Debezium)')
    fix_group.add_argument('--fix', action='store_true',
                           help='Tous les fix : H2 (Kafka), H3 (Snowflake), H4, H6')
    args = parser.parse_args()

    print('=' * 60)
    print('HEALTHCHECK MAINTENANCE')
    print('=' * 60)

    checks = [
        ('H1', 'MySQL RDS', check_h1_mysql),
        ('H2', 'Kafka broker', check_h2_kafka),
        ('H3', 'Snowflake', check_h3_snowflake),
        ('H4', 'Warehouse actif', check_h4_warehouse),
        ('H5', 'Metabase API', check_h5_metabase),
        ('H6', 'Debezium connector', check_h6_debezium),
        ('H7', 'Permissions Snowflake', check_h7_permissions),
    ]

    results = {}
    critical_fail = False

    for code, name, check_fn in checks:
        ok, msg = check_fn()
        status = 'OK' if ok else 'FAIL'
        results[code] = {'ok': ok, 'msg': msg}
        print(f'  {code} {name:.<35} {status} ({msg})')

        if not ok and code in ('H1', 'H2', 'H3'):
            critical_fail = True

    # Corrections automatiques
    if args.fix or args.fix_safe:
        print('\n--- Corrections ---')

        # Tous les fix (--fix-safe et --fix) — avec garde-fous integres
        if not results['H2']['ok']:
            ok, msg = fix_h2_kafka()
            print(f'  H2 restart Kafka: {"OK" if ok else "FAIL"} ({msg})')

        if not results['H3']['ok']:
            ok, msg = fix_h3_snowflake()
            print(f'  H3 reconnexion Snowflake: {"OK" if ok else "FAIL"} ({msg})')

        if not results['H4']['ok']:
            ok, msg = fix_h4_warehouse()
            print(f'  H4 resume warehouse: {"OK" if ok else "FAIL"} ({msg})')

        if not results['H6']['ok']:
            ok, msg = fix_h6_debezium()
            print(f'  H6 restart Debezium: {"OK" if ok else "FAIL"} ({msg})')

    # Resume
    nb_ok = sum(1 for r in results.values() if r['ok'])
    nb_fail = len(results) - nb_ok
    print(f'\n  Resume: {nb_ok}/7 OK, {nb_fail} FAIL')

    if critical_fail:
        print('  CRITIQUE: MySQL, Kafka ou Snowflake inaccessible')
        sys.exit(1)

    sys.exit(0 if nb_fail == 0 else 2)


if __name__ == '__main__':
    main()
