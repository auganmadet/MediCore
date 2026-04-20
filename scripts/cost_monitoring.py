"""Monitoring des couts Snowflake (credits consommes vs quota).

Interroge SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY pour les dernieres 24h,
agrege par warehouse, insere dans AUDIT.SNOWFLAKE_CREDITS, et envoie une alerte Teams
si le quota mensuel du Resource Monitor est proche d'etre atteint.

Prerequis :
- Resource Monitor MEDICORE_MONITOR cree et attache a MEDICORE_WH (cf DDL_WH.sql)
- Table AUDIT.SNOWFLAKE_CREDITS (cf DDL_TABLES.sql)
- GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE MEDICORE_DBT_EXECUTOR
- ACCOUNT_USAGE a un delai de ~45 min : les donnees du jour en cours sont incompletes.

Usage :
    python scripts/cost_monitoring.py                    # check + insert + alert si seuil
    python scripts/cost_monitoring.py --dry-run          # check uniquement
    python scripts/cost_monitoring.py --threshold 90     # alerte si >= 90% du quota
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

RESOURCE_MONITOR_NAME = os.getenv('SNOWFLAKE_RESOURCE_MONITOR', 'MEDICORE_MONITOR')
WAREHOUSE_NAME = os.getenv('SNOWFLAKE_WAREHOUSE', 'MEDICORE_WH')
DEFAULT_ALERT_THRESHOLD_PCT = int(os.getenv('SNOWFLAKE_ALERT_THRESHOLD_PCT', '75'))
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL', '').strip()


def get_connection():
    """Connexion Snowflake via ACCOUNTADMIN (requis pour SHOW RESOURCE MONITORS)."""
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        warehouse=WAREHOUSE_NAME,
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        role='ACCOUNTADMIN',
    )


def fetch_last_24h_usage(cursor):
    """Recupere la consommation des dernieres 24h par warehouse.

    Returns:
        Liste de dicts : [{warehouse, credits_used, credits_cloud}, ...]
    """
    cursor.execute(
        """
        SELECT
            WAREHOUSE_NAME,
            SUM(CREDITS_USED_COMPUTE)         AS credits_compute,
            SUM(CREDITS_USED_CLOUD_SERVICES)  AS credits_cloud,
            SUM(CREDITS_USED)                 AS credits_total,
            MIN(START_TIME)                   AS earliest,
            MAX(END_TIME)                     AS latest
        FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
        WHERE START_TIME >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
          AND WAREHOUSE_NAME IS NOT NULL
        GROUP BY WAREHOUSE_NAME
        ORDER BY credits_total DESC
        """
    )
    rows = cursor.fetchall()
    results = []
    for r in rows:
        results.append({
            'warehouse': r[0],
            'credits_compute': float(r[1] or 0),
            'credits_cloud': float(r[2] or 0),
            'credits_total': float(r[3] or 0),
            'earliest': r[4],
            'latest': r[5],
        })
    return results


def fetch_monitor_status(cursor, monitor_name):
    """Etat du Resource Monitor : credits utilises, restants, quota, frequency."""
    cursor.execute('SHOW RESOURCE MONITORS')
    cols = [d[0] for d in cursor.description]
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        if str(d.get('name')) == monitor_name:
            return {
                'name': d.get('name'),
                'credit_quota': float(d.get('credit_quota') or 0),
                'used_credits': float(d.get('used_credits') or 0),
                'remaining_credits': float(d.get('remaining_credits') or 0),
                'frequency': d.get('frequency'),
                'start_time': d.get('start_time'),
                'end_time': d.get('end_time'),
            }
    return None


def insert_audit_row(cursor, warehouse, credits_used, credits_cloud, monitor):
    """Insere ou met a jour la ligne du jour dans AUDIT.SNOWFLAKE_CREDITS.

    Cle : (USAGE_DATE, WAREHOUSE_NAME). MERGE pour idempotence si rerun dans la journee.
    """
    cursor.execute(
        """
        MERGE INTO MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS t
        USING (
            SELECT
                CURRENT_DATE() AS USAGE_DATE,
                %s AS WAREHOUSE_NAME,
                %s AS CREDITS_USED,
                %s AS CREDITS_USED_CLOUD_SERVICES,
                %s AS CREDITS_REMAINING,
                %s AS QUOTA_MONTHLY,
                %s AS PERIOD_START
        ) s
        ON t.USAGE_DATE = s.USAGE_DATE AND t.WAREHOUSE_NAME = s.WAREHOUSE_NAME
        WHEN MATCHED THEN UPDATE SET
            CREDITS_USED = s.CREDITS_USED,
            CREDITS_USED_CLOUD_SERVICES = s.CREDITS_USED_CLOUD_SERVICES,
            CREDITS_REMAINING = s.CREDITS_REMAINING,
            QUOTA_MONTHLY = s.QUOTA_MONTHLY,
            PERIOD_START = s.PERIOD_START,
            CREATED_AT = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
            USAGE_DATE, WAREHOUSE_NAME, CREDITS_USED, CREDITS_USED_CLOUD_SERVICES,
            CREDITS_REMAINING, QUOTA_MONTHLY, PERIOD_START
        ) VALUES (
            s.USAGE_DATE, s.WAREHOUSE_NAME, s.CREDITS_USED, s.CREDITS_USED_CLOUD_SERVICES,
            s.CREDITS_REMAINING, s.QUOTA_MONTHLY, s.PERIOD_START
        )
        """,
        (
            warehouse,
            credits_used,
            credits_cloud,
            monitor['remaining_credits'] if monitor else None,
            monitor['credit_quota'] if monitor else None,
            monitor['start_time'] if monitor else None,
        ),
    )


def send_teams_alert(monitor, pct_used, alert_level):
    """Envoie une alerte Teams (Adaptive Card) sur la consommation Snowflake.

    Args:
        monitor: Dict etat Resource Monitor.
        pct_used: Pourcentage quota utilise (0-100+).
        alert_level: 'WARNING' ou 'CRITICAL'.

    Returns:
        True si webhook OK, False sinon.
    """
    if not TEAMS_WEBHOOK_URL:
        logger.info('TEAMS_WEBHOOK_URL vide : alerte non envoyee')
        return False

    color = 'Warning' if alert_level == 'WARNING' else 'Attention'
    title = (
        f'Snowflake credits : {pct_used:.1f}% du quota utilise'
        f' ({alert_level})'
    )
    text = (
        f'**Warehouse** : {WAREHOUSE_NAME} | **Monitor** : {monitor["name"]}\n\n'
        f'**Quota** : {monitor["credit_quota"]:.0f} credits ({monitor["frequency"]})\n\n'
        f'**Utilises** : {monitor["used_credits"]:.2f} credits\n\n'
        f'**Restants** : {monitor["remaining_credits"]:.2f} credits\n\n'
        f'**Periode** : {monitor["start_time"]} -> {monitor["end_time"]}'
    )

    payload = {
        'type': 'message',
        'attachments': [{
            'contentType': 'application/vnd.microsoft.card.adaptive',
            'content': {
                'type': 'AdaptiveCard',
                'version': '1.2',
                'body': [
                    {'type': 'TextBlock', 'text': title, 'weight': 'Bolder',
                     'color': color, 'size': 'Medium'},
                    {'type': 'TextBlock', 'text': text, 'wrap': True},
                ],
            },
        }],
    }

    try:
        req = urllib.request.Request(
            TEAMS_WEBHOOK_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status in (200, 202)
            if ok:
                logger.info('Alerte Teams envoyee (HTTP %s)', resp.status)
            else:
                logger.warning('Teams webhook HTTP %s', resp.status)
            return ok
    except Exception as e:  # pylint: disable=broad-except
        logger.warning('Teams webhook echec : %s', e)
        return False


def run(dry_run=False, alert_threshold_pct=DEFAULT_ALERT_THRESHOLD_PCT):
    """Point d'entree principal.

    Args:
        dry_run: Si True, pas d'insert AUDIT, pas d'alerte Teams.
        alert_threshold_pct: Seuil declenchement alerte Teams (ex: 75 -> >= 75%).

    Returns:
        Dict avec statut et metriques.
    """
    conn = get_connection()
    cur = conn.cursor()
    result = {'status': 'OK', 'warehouses': [], 'monitor': None, 'alert_sent': False}

    try:
        monitor = fetch_monitor_status(cur, RESOURCE_MONITOR_NAME)
        result['monitor'] = monitor

        if monitor is None:
            logger.warning('Resource Monitor %s introuvable', RESOURCE_MONITOR_NAME)
            result['status'] = 'WARN'
        else:
            logger.info(
                '%s : %.2f / %.0f credits (%.2f%%)',
                monitor['name'], monitor['used_credits'], monitor['credit_quota'],
                100 * monitor['used_credits'] / max(monitor['credit_quota'], 1),
            )

        usages = fetch_last_24h_usage(cur)
        result['warehouses'] = usages
        for u in usages:
            logger.info(
                '24h %s : %.2f credits (compute=%.2f, cloud=%.2f)',
                u['warehouse'], u['credits_total'], u['credits_compute'], u['credits_cloud'],
            )

        if not dry_run:
            for u in usages:
                insert_audit_row(cur, u['warehouse'], u['credits_total'], u['credits_cloud'], monitor)
            logger.info('AUDIT.SNOWFLAKE_CREDITS : %d ligne(s) upsert', len(usages))

        if monitor and monitor['credit_quota'] > 0:
            pct = 100 * monitor['used_credits'] / monitor['credit_quota']
            if pct >= alert_threshold_pct:
                level = 'CRITICAL' if pct >= 90 else 'WARNING'
                logger.warning('Seuil atteint (%.1f%% >= %d%%) : alerte %s',
                               pct, alert_threshold_pct, level)
                if not dry_run:
                    result['alert_sent'] = send_teams_alert(monitor, pct, level)
            else:
                logger.info('Seuil %d%% non atteint (%.1f%%)', alert_threshold_pct, pct)
    finally:
        cur.close()
        conn.close()

    return result


def main():
    parser = argparse.ArgumentParser(description='Monitoring couts Snowflake')
    parser.add_argument('--dry-run', action='store_true',
                        help='Pas d insert AUDIT, pas d alerte Teams')
    parser.add_argument('--threshold', type=int, default=DEFAULT_ALERT_THRESHOLD_PCT,
                        help='Seuil pourcentage quota pour alerte Teams')
    args = parser.parse_args()

    try:
        result = run(dry_run=args.dry_run, alert_threshold_pct=args.threshold)
        if result['status'] != 'OK':
            sys.exit(1)
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('cost_monitoring.py : echec %s', e)
        sys.exit(2)


if __name__ == '__main__':
    main()
