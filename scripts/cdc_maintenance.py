"""Maintenance Phase 2 : verification CDC / Kafka.

Verifie l'etat du pipeline CDC :
- C1 : Kafka lag par topic (seuil configurable)
- C2 : DLQ en croissance (table _DLQ)
- C3 : Doublons dans les 4 tables CDC RAW
- C4 : Debezium connector en erreur
- C5 : Topics Kafka vides (0 events)
- C6 : Offsets Kafka non commites

S'auto-authentifie via .env. Lecture seule par defaut.

Usage :
    python scripts/cdc_maintenance.py
    python scripts/cdc_maintenance.py --fix       (purge DLQ > 90j, restart Debezium)
    python scripts/cdc_maintenance.py --dry-run   (detecte sans corriger)
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_GROUP_ID = os.getenv('CDC_KAFKA_GROUP_ID', 'medi_core_cdc_batch_dev2')
KAFKA_CONNECT_URL = os.getenv('KAFKA_CONNECT_URL', 'http://kafka_connect:8083')
CDC_TOPIC_PREFIX = os.getenv('CDC_KAFKA_TOPIC_PREFIX', 'winstat_rds.winstat')
CDC_TABLES = ['COMMANDES', 'FACTURES', 'ORDERS', 'MODSTOCK']
CDC_TOPICS = [f'{CDC_TOPIC_PREFIX}.{t}' for t in CDC_TABLES]
LAG_THRESHOLD = int(os.getenv('KAFKA_LAG_THRESHOLD', '10000'))
DLQ_THRESHOLD = int(os.getenv('DLQ_THRESHOLD', '100'))


def get_snowflake_conn():
    """Connexion Snowflake standard."""
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='RAW',
    )


def check_c1_kafka_lag():
    """C1 : lag Kafka par topic."""
    try:
        from kafka import KafkaConsumer, TopicPartition
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=KAFKA_GROUP_ID,
            enable_auto_commit=False,
            consumer_timeout_ms=5000,
        )

        lags = {}
        total = 0
        for topic in CDC_TOPICS:
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None:
                lags[topic] = -1
                continue
            tps = [TopicPartition(topic, p) for p in partitions]
            consumer.assign(tps)
            end_offsets = consumer.end_offsets(tps)
            topic_lag = 0
            for tp in tps:
                end = end_offsets.get(tp, 0)
                committed = consumer.committed(tp)
                committed = committed if committed is not None else 0
                topic_lag += max(0, end - committed)
            lags[topic] = topic_lag
            total += topic_lag

        consumer.close()
        lags['total'] = total
        ok = total <= LAG_THRESHOLD
        return ok, lags
    except ImportError:
        return False, {'error': 'kafka-python non installe'}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_c2_dlq():
    """C2 : nombre de lignes dans _DLQ."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()

        # Verifier si la table _DLQ existe
        # Lister les tables pour trouver _DLQ (nom avec underscore)
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME LIKE '%DLQ%'"
        )
        dlq_tables = [row[0] for row in cursor.fetchall()]

        if not dlq_tables:
            cursor.close()
            conn.close()
            return True, {'count': 0, 'status': 'aucune table DLQ trouvee (aucun event en erreur)'}

        dlq_name = dlq_tables[0]
        cursor.execute(f'SELECT COUNT(*) FROM RAW."{dlq_name}"')
        count = cursor.fetchone()[0]

        oldest = None
        if count > 0:
            try:
                cursor.execute(f'SELECT MIN(CDC_TIMESTAMP) FROM RAW."{dlq_name}"')
                oldest = cursor.fetchone()[0]
            except Exception:
                pass

        cursor.close()
        conn.close()
        ok = count <= DLQ_THRESHOLD
        return ok, {'count': count, 'oldest': str(oldest) if oldest else None}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_c3_duplicates():
    """C3 : doublons dans les 4 tables CDC RAW."""
    pk_map = {
        'RAW_COMMANDES': 'PHA_ID, COM_GROI, PRD_ID',
        'RAW_FACTURES': 'PHA_ID, FAC_ID, FAC_TI',
        'RAW_ORDERS': 'PHA_ID, FAC_ID',
        'RAW_MODSTOCK': 'PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP',
    }

    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        results = {}

        for table, pk in pk_map.items():
            # Snowflake ne supporte pas COUNT(DISTINCT (col1, col2))
            # Utiliser un GROUP BY + HAVING pour detecter les doublons
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            total = cursor.fetchone()[0]
            cursor.execute(
                f'SELECT COUNT(*) FROM ('
                f'SELECT {pk} FROM {table} GROUP BY {pk} HAVING COUNT(*) > 1'
                f')'
            )
            nb_dupes = cursor.fetchone()[0]
            results[table] = {'total': total, 'duplicates': nb_dupes}

        cursor.close()
        conn.close()

        has_dupes = any(r.get('duplicates', 0) > 0 for r in results.values())
        return not has_dupes, results
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_c4_debezium():
    """C4 : etat du connector Debezium."""
    try:
        req = urllib.request.Request(f'{KAFKA_CONNECT_URL}/connectors', method='GET')
        resp = urllib.request.urlopen(req, timeout=10)
        connectors = json.loads(resp.read())

        if not connectors:
            return False, {'status': 'aucun connector'}

        results = {}
        all_ok = True
        for name in connectors:
            req = urllib.request.Request(
                f'{KAFKA_CONNECT_URL}/connectors/{name}/status', method='GET',
            )
            resp = urllib.request.urlopen(req, timeout=10)
            status = json.loads(resp.read())
            state = status.get('connector', {}).get('state', '?')
            tasks = [t.get('state', '?') for t in status.get('tasks', [])]
            results[name] = {'state': state, 'tasks': tasks}
            if state != 'RUNNING' or any(t != 'RUNNING' for t in tasks):
                all_ok = False

        return all_ok, results
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_c5_empty_topics():
    """C5 : topics Kafka vides (end_offset = 0)."""
    try:
        from kafka import KafkaConsumer, TopicPartition
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            consumer_timeout_ms=5000,
        )

        empty = []
        for topic in CDC_TOPICS:
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None:
                empty.append(topic)
                continue
            tps = [TopicPartition(topic, p) for p in partitions]
            consumer.assign(tps)
            end_offsets = consumer.end_offsets(tps)
            total_msgs = sum(end_offsets.values())
            if total_msgs == 0:
                empty.append(topic)

        consumer.close()
        return len(empty) == 0, {'empty_topics': empty, 'total_topics': len(CDC_TOPICS)}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_c6_committed_offsets():
    """C6 : offsets Kafka commites (vs end_offset)."""
    try:
        from kafka import KafkaConsumer, TopicPartition
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=KAFKA_GROUP_ID,
            enable_auto_commit=False,
            consumer_timeout_ms=5000,
        )

        uncommitted = []
        for topic in CDC_TOPICS:
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None:
                continue
            tps = [TopicPartition(topic, p) for p in partitions]
            consumer.assign(tps)
            for tp in tps:
                committed = consumer.committed(tp)
                if committed is None:
                    uncommitted.append(f'{topic}[{tp.partition}]')

        consumer.close()
        return len(uncommitted) == 0, {'uncommitted': uncommitted}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def fix_c2_dlq_purge():
    """Purge les DLQ de plus de 90 jours."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM RAW._DLQ WHERE CDC_TIMESTAMP < DATEADD('day', -90, CURRENT_TIMESTAMP())"
        )
        deleted = cursor.rowcount
        cursor.close()
        conn.close()
        return True, f'{deleted} lignes purgees (> 90 jours)'
    except Exception as e:
        return False, str(e)[:100]


def fix_c4_debezium_restart():
    """Redemarrage du connector Debezium."""
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
    parser = argparse.ArgumentParser(description='CDC maintenance (C1-C6)')
    parser.add_argument('--fix', action='store_true', help='Corrige C2 (purge DLQ) et C4 (restart Debezium)')
    parser.add_argument('--dry-run', action='store_true', help='Detecte sans corriger')
    args = parser.parse_args()

    print('=' * 60)
    print('CDC MAINTENANCE')
    print('=' * 60)

    checks = [
        ('C1', 'Kafka lag par topic', check_c1_kafka_lag),
        ('C2', 'DLQ (Dead Letter Queue)', check_c2_dlq),
        ('C3', 'Doublons dans RAW CDC', check_c3_duplicates),
        ('C4', 'Debezium connector', check_c4_debezium),
        ('C5', 'Topics Kafka vides', check_c5_empty_topics),
        ('C6', 'Offsets Kafka commites', check_c6_committed_offsets),
    ]

    results = {}
    for code, name, check_fn in checks:
        ok, details = check_fn()
        status = 'OK' if ok else 'FAIL'
        results[code] = {'ok': ok, 'details': details}
        print(f'\n  {code} {name}')
        print(f'     Status: {status}')

        if isinstance(details, dict):
            for k, v in details.items():
                if k == 'error':
                    print(f'     Erreur: {v}')
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        print(f'     {k}.{k2}: {v2}')
                else:
                    print(f'     {k}: {v}')
        else:
            print(f'     Details: {details}')

    # Corrections
    if args.fix and not args.dry_run:
        print('\n--- Corrections ---')
        if not results.get('C2', {}).get('ok', True):
            ok, msg = fix_c2_dlq_purge()
            print(f'  C2 purge DLQ: {"OK" if ok else "FAIL"} ({msg})')

        if not results.get('C4', {}).get('ok', True):
            ok, msg = fix_c4_debezium_restart()
            print(f'  C4 restart Debezium: {"OK" if ok else "FAIL"} ({msg})')

    # Resume
    nb_ok = sum(1 for r in results.values() if r['ok'])
    nb_fail = len(results) - nb_ok
    print(f'\n{"=" * 60}')
    print(f'  Resume: {nb_ok}/6 OK, {nb_fail} FAIL')

    if nb_fail > 0:
        print('  Problemes detectes:')
        for code, r in results.items():
            if not r['ok']:
                print(f'    {code}: voir details ci-dessus')

    sys.exit(0 if nb_fail == 0 else 1)


if __name__ == '__main__':
    main()
