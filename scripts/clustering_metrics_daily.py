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

Persistance double :

- ``reports/clustering_metrics.csv`` (UPSERT par measure_date) pour visualisation
  rapide (Excel, Sheet, dbt source).
- ``MEDICORE_PROD.AUDIT.CLUSTERING_METRICS_DAILY`` (MERGE INTO par measure_date)
  pour requêtes SQL et rétention long terme.

Alerte Teams si TEAMS_WEBHOOK_URL est définie et qu'un seuil est franchi :

- ``merge_bulk_sec`` > 300 (ref_reload anormalement long)
- ``avg_depth`` > 6 (clustering dégradé)
- ``ac_credits_cumul`` augmente de > 0,1 cr depuis la veille (pic auto-clustering)

Usage :

    # Nuit J-1 par défaut (= la nuit qui vient de finir, données ACCOUNT_USAGE
    # disponibles à 09h après une nuit qui finit à 05h FR)
    python scripts/clustering_metrics_daily.py

    # Nuit spécifique
    python scripts/clustering_metrics_daily.py --date 2026-04-28

    # Backfill historique (plage de dates)
    python scripts/clustering_metrics_daily.py --since 2026-04-22 --until 2026-04-29

    # Sortie sans écriture (CSV + Snowflake) — vérification rapide
    python scripts/clustering_metrics_daily.py --date 2026-04-28 --no-write

    # Désactiver l'alerte Teams pour un run de test
    python scripts/clustering_metrics_daily.py --no-alert
"""

import argparse
import csv
import json
import logging
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
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

# Persistance Snowflake (table de série temporelle)
AUDIT_TABLE = 'MEDICORE_PROD.AUDIT.CLUSTERING_METRICS_DAILY'

# Alerte Teams (webhook optionnel via env var)
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL', '').strip()
ALERT_THRESHOLD_MERGE_BULK_SEC = 300.0
ALERT_THRESHOLD_AVG_DEPTH = 6.0
ALERT_THRESHOLD_AC_DELTA_CR = 0.1

CSV_PATH = Path(__file__).resolve().parent.parent / 'reports' / 'clustering_metrics.csv'
CSV_FIELDS = [
    'measure_date',          # Date d'analyse (jour de démarrage de la nuit en UTC)
    'collected_at',          # Timestamp de la mesure
    'merge_bulk_sec',        # MERGE INTO RAW_MEDIPRIX_FACTURES (mode INCR mar-sam)
    'merge_bulk_rows',       # Rows produced par le MERGE bulk
    'copy_bulk_sec',         # COPY INTO RAW_MEDIPRIX_FACTURES (mode FULL lundi)
    'copy_bulk_rows',        # Rows produced par le COPY bulk
    'merge_stg_sec',         # MERGE STAGING.stg_mediprix_factures (dbt staging)
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
    """Récupère la query la plus longue de la journée matchant le pattern.

    Args:
        cur: Curseur Snowflake (TIMEZONE='UTC' déjà set).
        day: Jour de démarrage de la nuit (UTC).
        query_pattern: Pattern ILIKE sur QUERY_TEXT.
        exclude_pattern: Pattern ILIKE à exclure (ex: 'STAGING' pour distinguer
            MERGE bulk_load de MERGE stg).

    Returns:
        Dict {sec, rows, query_id} ou {sec=None, rows=None} si non trouvé.

    Note sur le compteur ``rows`` :
        Pour un MERGE, ``ROWS_PRODUCED`` est un compteur ambigu Snowflake (peut
        inclure le scan de la cible, donne des valeurs absurdes ex 207 M sur 6,8 M
        rows réellement traitées). On utilise donc ``ROWS_INSERTED + ROWS_UPDATED
        + ROWS_DELETED`` qui reflète le vrai volume affecté.

        Pour un COPY INTO, ces 3 colonnes sont NULL, donc on retombe sur
        ``ROWS_PRODUCED`` qui est correct dans ce cas (= rows chargées).
    """
    start_window = datetime(day.year, day.month, day.day, 18, 0, 0)
    end_window = start_window + timedelta(hours=14)
    sql = """
        SELECT
            ROUND(TOTAL_ELAPSED_TIME/1000, 1) AS sec,
            COALESCE(
                NULLIF(
                    COALESCE(ROWS_INSERTED, 0) +
                    COALESCE(ROWS_UPDATED, 0) +
                    COALESCE(ROWS_DELETED, 0),
                    0
                ),
                ROWS_PRODUCED
            ) AS rows_affected,
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
    """Pipeline principal : collecte les 5 indicateurs pour la nuit du jour donné.

    Selon le mode du ref_reload (FULL le lundi, INCR mar-sam, SKIP dimanche), ce
    sont des queries Snowflake différentes qui sont effectuées sur la table cible :

    - **FULL (lundi)** : ``COPY INTO RAW_MEDIPRIX_FACTURES`` (chargement direct
      après TRUNCATE) → ``copy_bulk_sec`` rempli, ``merge_bulk_sec`` vide.
    - **INCR (mar-sam)** : ``COPY INTO ..._STG_INCR`` (table temporaire) puis
      ``MERGE INTO RAW_MEDIPRIX_FACTURES`` (upsert) → ``merge_bulk_sec`` rempli,
      ``copy_bulk_sec`` vide.
    """
    merge_bulk = fetch_merge_query(
        cur, day,
        query_pattern='%MERGE INTO RAW_MEDIPRIX_FACTURES%',
        exclude_pattern='%STAGING%',
    )
    # COPY INTO RAW_MEDIPRIX_FACTURES sans le STG_INCR temporaire du mode INCR
    copy_bulk = fetch_merge_query(
        cur, day,
        query_pattern='%COPY INTO RAW_MEDIPRIX_FACTURES%',
        exclude_pattern='%STG_INCR%',
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
        'collected_at':       datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'merge_bulk_sec':     merge_bulk['sec'],
        'merge_bulk_rows':    merge_bulk['rows'],
        'copy_bulk_sec':      copy_bulk['sec'],
        'copy_bulk_rows':     copy_bulk['rows'],
        'merge_stg_sec':      stg['sec'],
        'merge_stg_rows':     stg['rows'],
        'avg_depth':          clustering['avg_depth'],
        'total_partitions':   clustering['total_partitions'],
        'ac_credits_cumul':   costs['credits_cumul'],
        'ac_gb_reclustered':  costs['gb_reclustered'],
        'ac_runs_cumul':      costs['runs_cumul'],
    }


SNAPSHOT_FIELDS = (
    'avg_depth', 'total_partitions',
    'ac_credits_cumul', 'ac_gb_reclustered', 'ac_runs_cumul',
)


def upsert_csv(metrics: Dict, csv_path: Path, preserve_snapshot: bool = True) -> None:
    """UPSERT d'une ligne dans le CSV par ``measure_date`` (clé d'unicité).

    Comportement :

    - Toutes les lignes existantes avec la même ``measure_date`` sont supprimées
      (déduplique au passage les éventuels doublons hérités d'anciennes exécutions).
    - La nouvelle ligne est insérée à la fin.
    - Le CSV final est trié par ``measure_date`` croissant pour rester lisible.

    Args:
        metrics: Métriques à upserter.
        csv_path: Chemin du CSV.
        preserve_snapshot: Si True (défaut), préserve les valeurs snapshot
            (avg_depth, total_partitions, ac_*) déjà présentes dans la ligne
            existante. Évite qu'un backfill rétroactif n'écrase un snapshot
            historique avec la valeur actuelle (qui n'a plus de sens pour une
            date passée). Mettre à False pour forcer la mise à jour.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    by_date: Dict[str, Dict] = {}
    existing_for_date: Optional[Dict] = None
    if csv_path.exists():
        with csv_path.open('r', newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                # Si plusieurs lignes existent pour la même date, on garde la plus
                # récemment collectée (meilleure heuristique en cas de doublon).
                key = row['measure_date']
                if key not in by_date or row.get('collected_at', '') > by_date[key].get('collected_at', ''):
                    by_date[key] = row
        existing_for_date = by_date.get(metrics['measure_date'])

    if preserve_snapshot and existing_for_date:
        merged = dict(metrics)
        for field in SNAPSHOT_FIELDS:
            old_val = existing_for_date.get(field, '')
            if old_val not in (None, '', '0', '0.0'):
                merged[field] = old_val
        by_date[metrics['measure_date']] = merged
    else:
        by_date[metrics['measure_date']] = metrics

    rows = sorted(by_date.values(), key=lambda r: r['measure_date'])
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def upsert_snowflake(cur, metrics: Dict, preserve_snapshot: bool = True) -> None:
    """MERGE INTO MEDICORE_PROD.AUDIT.CLUSTERING_METRICS_DAILY par measure_date.

    Crée la table si absente.

    Args:
        cur: Curseur Snowflake.
        metrics: Métriques à upserter.
        preserve_snapshot: Si True (défaut), préserve les valeurs snapshot
            existantes (avg_depth, total_partitions, ac_*) en cible. Évite qu'un
            backfill n'écrase un snapshot historique avec la valeur actuelle.
            Implémenté via ``COALESCE(t.col, s.col)`` dans le UPDATE.
    """
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            MEASURE_DATE DATE NOT NULL,
            COLLECTED_AT TIMESTAMP_NTZ NOT NULL,
            MERGE_BULK_SEC FLOAT,
            MERGE_BULK_ROWS NUMBER,
            COPY_BULK_SEC FLOAT,
            COPY_BULK_ROWS NUMBER,
            MERGE_STG_SEC FLOAT,
            MERGE_STG_ROWS NUMBER,
            AVG_DEPTH FLOAT,
            TOTAL_PARTITIONS NUMBER,
            AC_CREDITS_CUMUL FLOAT,
            AC_GB_RECLUSTERED FLOAT,
            AC_RUNS_CUMUL NUMBER,
            PRIMARY KEY (MEASURE_DATE)
        )
        """
    )
    # Migrations idempotentes : ajoute les colonnes COPY_BULK_* si la table
    # existait avant le 29/04/2026 sans elles.
    for col, typ in [('COPY_BULK_SEC', 'FLOAT'), ('COPY_BULK_ROWS', 'NUMBER')]:
        try:
            cur.execute(f"ALTER TABLE {AUDIT_TABLE} ADD COLUMN {col} {typ}")
        except snowflake.connector.errors.ProgrammingError:
            pass  # colonne déjà présente
    # Avec preserve_snapshot=True, le UPDATE garde la valeur existante si elle
    # n'est pas NULL (COALESCE(t.col, s.col)). Avec False, il écrase systéma-
    # tiquement (s.col). Pour les colonnes "historiques" (sec/rows), toujours
    # écraser car c'est le but du backfill.
    snapshot_assign = (
        "COALESCE(t.{0}, s.{0})" if preserve_snapshot else "s.{0}"
    )
    cur.execute(
        f"""
        MERGE INTO {AUDIT_TABLE} t
        USING (SELECT
            %(measure_date)s::DATE        AS MEASURE_DATE,
            %(collected_at)s::TIMESTAMP_NTZ AS COLLECTED_AT,
            %(merge_bulk_sec)s            AS MERGE_BULK_SEC,
            %(merge_bulk_rows)s           AS MERGE_BULK_ROWS,
            %(copy_bulk_sec)s             AS COPY_BULK_SEC,
            %(copy_bulk_rows)s            AS COPY_BULK_ROWS,
            %(merge_stg_sec)s             AS MERGE_STG_SEC,
            %(merge_stg_rows)s            AS MERGE_STG_ROWS,
            %(avg_depth)s                 AS AVG_DEPTH,
            %(total_partitions)s          AS TOTAL_PARTITIONS,
            %(ac_credits_cumul)s          AS AC_CREDITS_CUMUL,
            %(ac_gb_reclustered)s         AS AC_GB_RECLUSTERED,
            %(ac_runs_cumul)s             AS AC_RUNS_CUMUL
        ) s
        ON t.MEASURE_DATE = s.MEASURE_DATE
        WHEN MATCHED THEN UPDATE SET
            COLLECTED_AT = s.COLLECTED_AT,
            MERGE_BULK_SEC = s.MERGE_BULK_SEC,
            MERGE_BULK_ROWS = s.MERGE_BULK_ROWS,
            COPY_BULK_SEC = s.COPY_BULK_SEC,
            COPY_BULK_ROWS = s.COPY_BULK_ROWS,
            MERGE_STG_SEC = s.MERGE_STG_SEC,
            MERGE_STG_ROWS = s.MERGE_STG_ROWS,
            AVG_DEPTH = {snapshot_assign.format("AVG_DEPTH")},
            TOTAL_PARTITIONS = {snapshot_assign.format("TOTAL_PARTITIONS")},
            AC_CREDITS_CUMUL = {snapshot_assign.format("AC_CREDITS_CUMUL")},
            AC_GB_RECLUSTERED = {snapshot_assign.format("AC_GB_RECLUSTERED")},
            AC_RUNS_CUMUL = {snapshot_assign.format("AC_RUNS_CUMUL")}
        WHEN NOT MATCHED THEN INSERT (
            MEASURE_DATE, COLLECTED_AT, MERGE_BULK_SEC, MERGE_BULK_ROWS,
            COPY_BULK_SEC, COPY_BULK_ROWS,
            MERGE_STG_SEC, MERGE_STG_ROWS, AVG_DEPTH, TOTAL_PARTITIONS,
            AC_CREDITS_CUMUL, AC_GB_RECLUSTERED, AC_RUNS_CUMUL
        ) VALUES (
            s.MEASURE_DATE, s.COLLECTED_AT, s.MERGE_BULK_SEC, s.MERGE_BULK_ROWS,
            s.COPY_BULK_SEC, s.COPY_BULK_ROWS,
            s.MERGE_STG_SEC, s.MERGE_STG_ROWS, s.AVG_DEPTH, s.TOTAL_PARTITIONS,
            s.AC_CREDITS_CUMUL, s.AC_GB_RECLUSTERED, s.AC_RUNS_CUMUL
        )
        """,
        metrics,
    )


def detect_anomalies(cur, metrics: Dict) -> List[str]:
    """Détecte les anomalies par seuils + comparaison avec la veille.

    Args:
        cur: Curseur Snowflake (lit la mesure de la veille pour delta AC).
        metrics: Métriques du jour à comparer.

    Returns:
        Liste de messages d'anomalie (vide si nominale).
    """
    issues: List[str] = []
    if metrics.get('merge_bulk_sec') and metrics['merge_bulk_sec'] > ALERT_THRESHOLD_MERGE_BULK_SEC:
        issues.append(
            f"merge_bulk_sec = {metrics['merge_bulk_sec']:.1f} s "
            f"(seuil {ALERT_THRESHOLD_MERGE_BULK_SEC:.0f} s)"
        )
    if metrics.get('avg_depth', 0) > ALERT_THRESHOLD_AVG_DEPTH:
        issues.append(
            f"avg_depth = {metrics['avg_depth']:.2f} "
            f"(seuil {ALERT_THRESHOLD_AVG_DEPTH:.0f}) — clustering dégradé"
        )
    cur.execute(
        f"SELECT AC_CREDITS_CUMUL FROM {AUDIT_TABLE} "
        f"WHERE MEASURE_DATE < %s ORDER BY MEASURE_DATE DESC LIMIT 1",
        (metrics['measure_date'],),
    )
    row = cur.fetchone()
    if row is not None and row[0] is not None:
        delta = float(metrics['ac_credits_cumul']) - float(row[0])
        if delta > ALERT_THRESHOLD_AC_DELTA_CR:
            issues.append(
                f"ac_credits delta = +{delta:.3f} cr en 1 jour "
                f"(seuil +{ALERT_THRESHOLD_AC_DELTA_CR} cr) — pic auto-clustering"
            )
    return issues


def send_teams_alert(metrics: Dict, issues: List[str]) -> bool:
    """Envoie une alerte Teams (Adaptive Card) si webhook défini et anomalies.

    Returns:
        True si envoyé, False sinon (webhook absent ou pas d'anomalie).
    """
    if not TEAMS_WEBHOOK_URL or not issues:
        return False
    title = f"Clustering RAW_MEDIPRIX_FACTURES — anomalie {metrics['measure_date']}"
    body = "\n\n".join([f"- {i}" for i in issues])
    text = (
        f"**Mesure** : {metrics['measure_date']}\n\n"
        f"**Anomalies détectées** :\n\n{body}\n\n"
        f"**Métriques** : merge_bulk={metrics.get('merge_bulk_sec')}s, "
        f"avg_depth={metrics['avg_depth']}, "
        f"ac_credits_cumul={metrics['ac_credits_cumul']} cr"
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
                     'color': 'Attention', 'size': 'Medium'},
                    {'type': 'TextBlock', 'text': text, 'wrap': True},
                ],
            },
        }],
    }
    req = urllib.request.Request(
        TEAMS_WEBHOOK_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 202)
    except Exception as e:
        logger.warning('Teams webhook échec : %s', e)
        return False


def _fmt_sec(v: Optional[float]) -> str:
    return f"{v:>7.1f}s" if v is not None else "    n/a"


def _fmt_rows(v: Optional[int]) -> str:
    return f"{v:>11,}" if v is not None else "        n/a"


def render_text(metrics: Dict) -> str:
    """Format texte ligne pour affichage console."""
    return (
        f"{metrics['measure_date']} | "
        f"merge_bulk={_fmt_sec(metrics['merge_bulk_sec'])} | "
        f"copy_bulk={_fmt_sec(metrics['copy_bulk_sec'])} | "
        f"merge_stg={_fmt_sec(metrics['merge_stg_sec'])} | "
        f"avg_depth={metrics['avg_depth']:.4f} | "
        f"AC={metrics['ac_credits_cumul']:.3f}cr ({metrics['ac_gb_reclustered']:.1f}GB / {metrics['ac_runs_cumul']} runs)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Collecte quotidienne métriques clustering MEDIPRIX')
    parser.add_argument('--date', type=str, default=None,
                        help='Date de la nuit (YYYY-MM-DD UTC). Défaut : J-1 (la nuit qui vient de finir)')
    parser.add_argument('--since', type=str, default=None,
                        help='Backfill : date de début (YYYY-MM-DD)')
    parser.add_argument('--until', type=str, default=None,
                        help='Backfill : date de fin (YYYY-MM-DD, inclus)')
    parser.add_argument('--no-write', action='store_true',
                        help='Pas d\'écriture (CSV ni Snowflake) — vérification rapide')
    parser.add_argument('--no-alert', action='store_true',
                        help='Désactive l\'alerte Teams (run de test)')
    parser.add_argument('--no-preserve-snapshot', action='store_true',
                        help='Force l\'écrasement des colonnes snapshot (avg_depth, '
                             'total_partitions, ac_*) même si déjà présentes. Par '
                             'défaut, un re-run sur date passée préserve le snapshot '
                             'historique pour ne pas le polluer avec la valeur actuelle.')
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
        until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=1)
        days = date_range(since, until)
    elif args.date:
        days = [date.fromisoformat(args.date)]
    else:
        days = [date.today() - timedelta(days=1)]

    alerts_sent = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER SESSION SET TIMEZONE = 'UTC'")
        for day in days:
            metrics = collect_metrics(cur, day)
            print(render_text(metrics))
            if not args.no_write:
                preserve = not args.no_preserve_snapshot
                upsert_csv(metrics, csv_path, preserve_snapshot=preserve)
                upsert_snowflake(cur, metrics, preserve_snapshot=preserve)
            if not args.no_alert and not args.no_write:
                issues = detect_anomalies(cur, metrics)
                if issues:
                    logger.warning('Anomalies détectées (%s) : %s', day, ' | '.join(issues))
                    if send_teams_alert(metrics, issues):
                        alerts_sent += 1
    finally:
        cur.close()
        conn.close()

    if not args.no_write:
        logger.info(
            'Métriques sauvegardées : %s + %s (%d jour(s)) | %d alerte(s) Teams envoyée(s)',
            csv_path, AUDIT_TABLE, len(days), alerts_sent,
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
