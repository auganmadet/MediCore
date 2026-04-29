"""Collecte quotidienne des métriques clustering RAW_MEDIPRIX_FACTURES.

Mesure 4 indicateurs clés pour suivre l'effet du clustering au fil des nuits :

1. **MERGE bulk_load INTO RAW_MEDIPRIX_FACTURES** : durée du MERGE Snowflake qui
   upserte le staging incremental dans la table RAW. Mesuré via QUERY_HISTORY.
2. **MERGE STAGING.stg_mediprix_factures** : durée du MERGE dbt staging qui dédup
   les CDC events. Mesuré via QUERY_HISTORY.
3. **avg_depth clustering** : profondeur moyenne de chevauchement des micro-
   partitions. Plus c'est bas, mieux c'est. Mesuré via SYSTEM$CLUSTERING_INFORMATION.
4. **Auto-clustering cumulé** : crédits Snowflake consommés par le service serverless
   depuis l'ALTER CLUSTER BY (2026-04-27 09:28 UTC). Mesuré via
   AUTOMATIC_CLUSTERING_HISTORY.

Persistance : append dans ``reports/clustering_metrics.csv`` pour permettre une
analyse temporelle (Excel, Sheet, dbt source).

Usage :

    # Nuit J-2 par défaut (latence ACCOUNT_USAGE 45 min - 3 h)
    python scripts/clustering_metrics_daily.py

    # Nuit spécifique
    python scripts/clustering_metrics_daily.py --date 2026-04-28

    # Backfill historique (plage de dates)
    python scripts/clustering_metrics_daily.py --since 2026-04-22 --until 2026-04-29

    # Sortie sans écriture CSV (vérification rapide)
    python scripts/clustering_metrics_daily.py --date 2026-04-28 --no-write
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

WAREHOUSE_NAME = os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH')
TABLE_NAME = 'RAW_MEDIPRIX_FACTURES'
CLUSTER_KEY = '(PHA_ID, FAC_DATE)'
CLUSTERING_START = '2026-04-27 09:28:00'

CSV_PATH = Path(__file__).resolve().parent.parent / 'reports' / 'clustering_metrics.csv'
CSV_FIELDS = [
    'measure_date',          # Date d'analyse (jour de démarrage de la nuit en UTC)
    'collected_at',          # Timestamp de la mesure
    'merge_bulk_sec',        # Durée MERGE INTO RAW_MEDIPRIX_FACTURES
    'merge_bulk_rows',       # Rows produced par le MERGE bulk
    'merge_stg_sec',         # Durée MERGE STAGING.stg_mediprix_factures
    'merge_stg_rows',        # Rows produced par le MERGE stg
    'avg_depth',             # SYSTEM$CLUSTERING_INFORMATION average_depth
    'total_partitions',      # Nombre de micro-partitions
    'ac_credits_cumul',      # Crédits auto-clustering cumulés depuis ALTER
    'ac_gb_reclustered',     # GB reclustered cumulés depuis ALTER
    'ac_runs_cumul',         # Nombre de runs auto-clustering depuis ALTER
]


def get_connection() -> snowflake.connector.SnowflakeConnection:
    """Connexion Snowflake en rôle ACCOUNTADMIN (requis pour ACCOUNT_USAGE)."""
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        warehouse=WAREHOUSE_NAME,
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        role='ACCOUNTADMIN',
    )


def fetch_merge_query(cur, day: date, query_pattern: str, exclude_pattern: Optional[str]) -> Dict:
    """Récupère le MERGE le plus long de la journée matchant le pattern.

    Args:
        cur: Curseur Snowflake (TIMEZONE='UTC' déjà set).
        day: Jour de démarrage de la nuit (UTC).
        query_pattern: Pattern ILIKE sur QUERY_TEXT.
        exclude_pattern: Pattern ILIKE à exclure (ex: 'STAGING' pour distinguer
            MERGE bulk_load de MERGE stg).

    Returns:
        Dict {sec, rows, query_id} ou {sec=None, rows=None} si non trouvé.
    """
    start_window = datetime(day.year, day.month, day.day, 18, 0, 0)
    end_window = start_window + timedelta(hours=14)
    sql = """
        SELECT
            ROUND(TOTAL_ELAPSED_TIME/1000, 1) AS sec,
            ROWS_PRODUCED,
            QUERY_ID
        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
        WHERE WAREHOUSE_NAME = %s
          AND START_TIME >= %s
          AND START_TIME <  %s
          AND QUERY_TEXT ILIKE %s
    """
    params: List[Any] = [WAREHOUSE_NAME, start_window, end_window, query_pattern]
    if exclude_pattern:
        sql += " AND QUERY_TEXT NOT ILIKE %s"
        params.append(exclude_pattern)
    sql += " ORDER BY TOTAL_ELAPSED_TIME DESC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return {'sec': None, 'rows': None, 'query_id': None}
    return {'sec': float(row[0] or 0), 'rows': int(row[1] or 0), 'query_id': row[2]}


def fetch_clustering_info(cur) -> Dict:
    """État actuel du clustering RAW_MEDIPRIX_FACTURES (instantané)."""
    cur.execute(
        f"SELECT SYSTEM$CLUSTERING_INFORMATION('MEDICORE_PROD.RAW.{TABLE_NAME}', '{CLUSTER_KEY}')"
    )
    info = json.loads(cur.fetchone()[0])
    return {
        'avg_depth': float(info.get('average_depth', 0) or 0),
        'total_partitions': int(info.get('total_partition_count', 0) or 0),
    }


def fetch_clustering_costs(cur) -> Dict:
    """Coûts cumulés auto-clustering depuis l'ALTER CLUSTER BY initial."""
    cur.execute(
        """
        SELECT
            ROUND(SUM(CREDITS_USED), 4),
            ROUND(SUM(NUM_BYTES_RECLUSTERED)/POWER(1024, 3), 2),
            COUNT(*)
        FROM SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY
        WHERE TABLE_NAME = %s
          AND START_TIME >= %s::TIMESTAMP_NTZ
        """,
        (TABLE_NAME, CLUSTERING_START),
    )
    row = cur.fetchone()
    return {
        'credits_cumul': float(row[0] or 0),
        'gb_reclustered': float(row[1] or 0),
        'runs_cumul': int(row[2] or 0),
    }


def collect_metrics(cur, day: date) -> Dict:
    """Pipeline principal : collecte les 4 indicateurs pour la nuit du jour donné."""
    bulk = fetch_merge_query(
        cur, day,
        query_pattern='%MERGE INTO RAW_MEDIPRIX_FACTURES%',
        exclude_pattern='%STAGING%',
    )
    stg = fetch_merge_query(
        cur, day,
        query_pattern='%merge into MEDICORE_PROD.STAGING.stg_mediprix_factures%',
        exclude_pattern=None,
    )
    clustering = fetch_clustering_info(cur)
    costs = fetch_clustering_costs(cur)
    return {
        'measure_date':       day.isoformat(),
        'collected_at':       datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'merge_bulk_sec':     bulk['sec'],
        'merge_bulk_rows':    bulk['rows'],
        'merge_stg_sec':      stg['sec'],
        'merge_stg_rows':     stg['rows'],
        'avg_depth':          clustering['avg_depth'],
        'total_partitions':   clustering['total_partitions'],
        'ac_credits_cumul':   costs['credits_cumul'],
        'ac_gb_reclustered':  costs['gb_reclustered'],
        'ac_runs_cumul':      costs['runs_cumul'],
    }


def append_csv(metrics: Dict, csv_path: Path) -> None:
    """Append d'une ligne dans le CSV (création si absent, header inclus)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with csv_path.open('a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(metrics)


def _fmt_sec(v: Optional[float]) -> str:
    return f"{v:>7.1f}s" if v is not None else "    n/a"


def _fmt_rows(v: Optional[int]) -> str:
    return f"{v:>11,}" if v is not None else "        n/a"


def render_text(metrics: Dict) -> str:
    """Format texte ligne pour affichage console."""
    return (
        f"{metrics['measure_date']} | "
        f"merge_bulk={_fmt_sec(metrics['merge_bulk_sec'])} ({_fmt_rows(metrics['merge_bulk_rows'])}) | "
        f"merge_stg={_fmt_sec(metrics['merge_stg_sec'])} ({_fmt_rows(metrics['merge_stg_rows'])}) | "
        f"avg_depth={metrics['avg_depth']:.4f} | "
        f"AC={metrics['ac_credits_cumul']:.3f}cr ({metrics['ac_gb_reclustered']:.1f}GB / {metrics['ac_runs_cumul']} runs)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Collecte quotidienne métriques clustering MEDIPRIX')
    parser.add_argument('--date', type=str, default=None,
                        help='Date de la nuit (YYYY-MM-DD UTC). Défaut : J-2 (latence ACCOUNT_USAGE)')
    parser.add_argument('--since', type=str, default=None,
                        help='Backfill : date de début (YYYY-MM-DD)')
    parser.add_argument('--until', type=str, default=None,
                        help='Backfill : date de fin (YYYY-MM-DD, inclus)')
    parser.add_argument('--no-write', action='store_true',
                        help='Pas d\'écriture CSV (vérification rapide)')
    parser.add_argument('--csv', type=str, default=str(CSV_PATH),
                        help=f'Chemin CSV (défaut {CSV_PATH})')
    return parser.parse_args()


def date_range(since: date, until: date) -> List[date]:
    """Liste de dates inclusives [since, until]."""
    days = []
    d = since
    while d <= until:
        days.append(d)
        d += timedelta(days=1)
    return days


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)

    if args.since:
        since = date.fromisoformat(args.since)
        until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=2)
        days = date_range(since, until)
    elif args.date:
        days = [date.fromisoformat(args.date)]
    else:
        days = [date.today() - timedelta(days=2)]

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER SESSION SET TIMEZONE = 'UTC'")
        for day in days:
            metrics = collect_metrics(cur, day)
            print(render_text(metrics))
            if not args.no_write:
                append_csv(metrics, csv_path)
    finally:
        cur.close()
        conn.close()

    if not args.no_write:
        logger.info('Métriques sauvegardées : %s (%d ligne(s) ajoutée(s))', csv_path, len(days))
    return 0


if __name__ == '__main__':
    sys.exit(main())
