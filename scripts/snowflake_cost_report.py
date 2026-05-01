"""Rapport coût Snowflake détaillé par phase pour le traitement de nuit MediCore.

Décompose la consommation de crédits Snowflake en phases du traitement nocturne
(pre-night healthcheck, CDC pre-reload, audit Metabase, ref_reload, dbt post-reload,
pipeline_maintenance, dev_clone) en croisant deux tables Snowflake :

- ``SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`` : facturation warehouse par
  tranche d'1 h UTC (source de vérité pour le coût € facturé)
- ``SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY`` : facturation séparée du
  service auto-clustering (déclenché par CLUSTER BY après chaque COPY INTO ou CTAS)

Méthodologie :

- Tarif Mediprix : 2,76 €/crédit (paramétrable via --tarif)
- Fenêtre : J 18:00 UTC -> J+1 04:00 UTC (couvre 20:00 -> 06:00 FR)
- TIMEZONE forcé à UTC dans la session pour éviter les ambiguïtés Pacific
- Phase dominante par tranche horaire UTC selon le mapping ``PHASE_MAPPING``
- Auto-clustering attribué aux phases qui les déclenchent (MEDIPRIX -> ref_reload,
  MART_KPI_DORMANT -> dbt post-reload)

Modes du ref_reload (déterminés automatiquement via le jour de la semaine) :

- ``full`` (lundi)        : ref_reload complet sur 14 tables, ~5 h 17 min wall-clock
- ``incremental`` (mar-sam) : ref_reload incremental (~53 min) + cycles CDC nuit visibles
- ``skip`` (dimanche)     : pas de ref_reload, juste healthcheck + cycles CDC nuit

Le mapping libellé/tranche horaire diffère selon le mode car les phases ne tombent
pas dans les mêmes tranches UTC. Le total crédits est cohérent dans tous les cas.

Usage :

    # Nuit la plus récente avec données complètes (avant-hier UTC, mode auto)
    python scripts/snowflake_cost_report.py

    # Nuit spécifique (date = jour de démarrage en UTC)
    python scripts/snowflake_cost_report.py --date 2026-04-27

    # Forcer un mode (utile si le batch_loop s'écarte du calendrier hebdo standard)
    python scripts/snowflake_cost_report.py --date 2026-04-25 --mode incremental

    # Tarif différent + sortie JSON pour intégration
    python scripts/snowflake_cost_report.py --tarif 2.50 --json

    # Sauvegarde du rapport dans un fichier markdown
    python scripts/snowflake_cost_report.py --markdown reports/cost_2026-04-27.md
"""

import argparse
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

DEFAULT_TARIF_EUR_PER_CREDIT = 2.76
WAREHOUSE_NAME = os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH')

# Mapping tranche horaire UTC -> phase dominante, par mode du traitement de nuit.
# - FULL : nuit du lundi (DOW=1), ref_reload complet sur 14 tables, ~5h17 wall-clock.
#   Calé sur la timeline batch_loop.sh observée le 27/04/2026.
# - INCREMENTAL : nuits mar-sam (DOW=2..6), ref_reload incremental ~53 min wall-clock.
#   Les cycles CDC nuit (DBT_EVERY_N=12, toutes les 2h) deviennent visibles dans
#   les tranches 23:00-04:00 UTC (~0,1 cr par cycle).
# - SKIP : nuit du dimanche (DOW=0), pas de ref_reload, juste healthcheck + cycles CDC.

PHASE_MAPPING_FULL: List[Dict[str, Any]] = [
    {'hour_utc': 18, 'phase': 'Pre-night healthcheck',                  'fr': '20:00-21:00'},
    {'hour_utc': 19, 'phase': 'CDC pre-reload',                         'fr': '21:00-22:00'},
    {'hour_utc': 20, 'phase': 'Audit purge + backup Metabase',          'fr': '22:00-23:00'},
    {'hour_utc': 21, 'phase': 'ref_reload : début (TRUNCATE + PUT)',    'fr': '23:00-00:00'},
    {'hour_utc': 22, 'phase': 'ref_reload : SELECT MySQL (WH suspendu)', 'fr': '00:00-01:00'},
    {'hour_utc': 23, 'phase': 'ref_reload : SELECT MySQL (WH suspendu)', 'fr': '01:00-02:00'},
    {'hour_utc': 0,  'phase': 'ref_reload : SELECT MySQL (WH suspendu)', 'fr': '02:00-03:00'},
    {'hour_utc': 1,  'phase': 'ref_reload : COPY MEDIPRIX + PRODUITS',  'fr': '03:00-04:00'},
    {'hour_utc': 2,  'phase': 'ref_reload fin + POST-CHECK + dbt post-reload début', 'fr': '04:00-05:00'},
    {'hour_utc': 3,  'phase': 'dbt post-reload fin + pipeline_maintenance + dev_clone', 'fr': '05:00-06:00'},
]

PHASE_MAPPING_INCREMENTAL: List[Dict[str, Any]] = [
    {'hour_utc': 18, 'phase': 'Pre-night healthcheck',                                     'fr': '20:00-21:00'},
    {'hour_utc': 19, 'phase': 'CDC pre-reload',                                            'fr': '21:00-22:00'},
    {'hour_utc': 20, 'phase': 'Audit purge + backup Metabase',                             'fr': '22:00-23:00'},
    {'hour_utc': 21, 'phase': 'ref_reload INCREMENTAL (~53 min) + dbt post-reload début',  'fr': '23:00-00:00'},
    {'hour_utc': 22, 'phase': 'dbt post-reload fin + pipeline_maintenance + dev_clone',    'fr': '00:00-01:00'},
    {'hour_utc': 23, 'phase': 'Cycle CDC nuit (DBT_EVERY_N)',                              'fr': '01:00-02:00'},
    {'hour_utc': 0,  'phase': 'Cycle CDC nuit (DBT_EVERY_N)',                              'fr': '02:00-03:00'},
    {'hour_utc': 1,  'phase': 'Cycle CDC nuit (DBT_EVERY_N)',                              'fr': '03:00-04:00'},
    {'hour_utc': 2,  'phase': 'Cycle CDC nuit (DBT_EVERY_N)',                              'fr': '04:00-05:00'},
    {'hour_utc': 3,  'phase': 'Cycle CDC nuit + transition mode jour',                     'fr': '05:00-06:00'},
]

PHASE_MAPPING_SKIP: List[Dict[str, Any]] = [
    {'hour_utc': 18, 'phase': 'Pre-night healthcheck',                                     'fr': '20:00-21:00'},
    {'hour_utc': 19, 'phase': 'CDC pre-reload',                                            'fr': '21:00-22:00'},
    {'hour_utc': 20, 'phase': 'Audit purge + backup Metabase',                             'fr': '22:00-23:00'},
    {'hour_utc': 21, 'phase': 'Cycle CDC nuit (ref_reload SKIP dimanche)',                 'fr': '23:00-00:00'},
    {'hour_utc': 22, 'phase': 'Cycle CDC nuit',                                            'fr': '00:00-01:00'},
    {'hour_utc': 23, 'phase': 'Cycle CDC nuit',                                            'fr': '01:00-02:00'},
    {'hour_utc': 0,  'phase': 'Cycle CDC nuit',                                            'fr': '02:00-03:00'},
    {'hour_utc': 1,  'phase': 'Cycle CDC nuit',                                            'fr': '03:00-04:00'},
    {'hour_utc': 2,  'phase': 'Cycle CDC nuit',                                            'fr': '04:00-05:00'},
    {'hour_utc': 3,  'phase': 'Cycle CDC nuit + transition mode jour',                     'fr': '05:00-06:00'},
]

PHASE_MAPPINGS: Dict[str, List[Dict[str, Any]]] = {
    'full':        PHASE_MAPPING_FULL,
    'incremental': PHASE_MAPPING_INCREMENTAL,
    'skip':        PHASE_MAPPING_SKIP,
}

# Mode par défaut selon le jour de la semaine de la nuit qui démarre (date_anchor)
# DOW Python : Monday=0, Sunday=6 (méthode date.weekday())
MODE_BY_WEEKDAY: Dict[int, str] = {
    0: 'full',         # Lundi -> nuit du lundi au mardi : full reload (DOW batch=1)
    1: 'incremental',  # Mardi
    2: 'incremental',  # Mercredi
    3: 'incremental',  # Jeudi
    4: 'incremental',  # Vendredi
    5: 'incremental',  # Samedi
    6: 'skip',         # Dimanche -> nuit du dimanche au lundi : skip
}

# Auto-clustering -> phase d'attribution (mêmes pour tous les modes : la table
# clusterée détermine le déclencheur, indépendamment du libellé de phase).
CLUSTERING_PHASE_MAPPING: Dict[str, Dict[str, str]] = {
    'full': {
        'RAW_MEDIPRIX_FACTURES': 'ref_reload : COPY MEDIPRIX + PRODUITS',
        'RAW_STOCKHISTORY':      'ref_reload fin + POST-CHECK + dbt post-reload début',
        'MART_KPI_DORMANT':      'dbt post-reload fin + pipeline_maintenance + dev_clone',
    },
    'incremental': {
        'RAW_MEDIPRIX_FACTURES': 'ref_reload INCREMENTAL (~53 min) + dbt post-reload début',
        'RAW_STOCKHISTORY':      'ref_reload INCREMENTAL (~53 min) + dbt post-reload début',
        'MART_KPI_DORMANT':      'dbt post-reload fin + pipeline_maintenance + dev_clone',
    },
    'skip': {
        # Pas de ref_reload donc pas de re-clustering massif. Si MART_KPI_DORMANT
        # apparaît c'est via le mode jour précédent — non attribué ici.
    },
}


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


def fetch_metering(cur, start_utc: datetime, end_utc: datetime, warehouse: str) -> List[Dict]:
    """Récupère les tranches horaires WAREHOUSE_METERING_HISTORY sur la fenêtre.

    Args:
        cur: Curseur Snowflake (TIMEZONE doit être 'UTC' pour la session).
        start_utc: Borne inférieure inclusive (NTZ interprété en UTC).
        end_utc: Borne supérieure exclusive.
        warehouse: Nom du warehouse à filtrer.

    Returns:
        Liste de dicts {hour_utc, compute, cloud, total} triés par START_TIME.
    """
    cur.execute(
        """
        SELECT
            START_TIME::TIMESTAMP_NTZ AS hour_utc,
            ROUND(CREDITS_USED_COMPUTE, 4)        AS cr_compute,
            ROUND(CREDITS_USED_CLOUD_SERVICES, 4) AS cr_cloud,
            ROUND(CREDITS_USED, 4)                AS cr_total
        FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
        WHERE WAREHOUSE_NAME = %s
          AND START_TIME >= %s
          AND START_TIME <  %s
        ORDER BY START_TIME
        """,
        (warehouse, start_utc, end_utc),
    )
    return [
        {'hour_utc': r[0], 'compute': float(r[1] or 0),
         'cloud':    float(r[2] or 0), 'total':   float(r[3] or 0)}
        for r in cur.fetchall()
    ]


def fetch_clustering(cur, start_utc: datetime, end_utc: datetime) -> List[Dict]:
    """Récupère les coûts d'auto-clustering sur la fenêtre.

    Args:
        cur: Curseur Snowflake.
        start_utc: Borne inférieure inclusive.
        end_utc: Borne supérieure exclusive.

    Returns:
        Liste de dicts {hour_utc, table_name, credits} (crédits > 0 uniquement).
    """
    cur.execute(
        """
        SELECT
            START_TIME::TIMESTAMP_NTZ AS hour_utc,
            TABLE_NAME,
            ROUND(CREDITS_USED, 4) AS credits
        FROM SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY
        WHERE START_TIME >= %s
          AND START_TIME <  %s
          AND CREDITS_USED > 0
        ORDER BY START_TIME
        """,
        (start_utc, end_utc),
    )
    return [
        {'hour_utc': r[0], 'table_name': r[1], 'credits': float(r[2] or 0)}
        for r in cur.fetchall()
    ]


def build_phases(metering: List[Dict], clustering: List[Dict], mode: str) -> List[Dict]:
    """Agrège les crédits par phase batch_loop.sh selon le mode du jour.

    Args:
        metering: Sortie de :func:`fetch_metering`.
        clustering: Sortie de :func:`fetch_clustering`.
        mode: 'full' (lundi), 'incremental' (mar-sam) ou 'skip' (dimanche).

    Returns:
        Liste de phases avec total crédits warehouse + auto-clustering attribués.
    """
    mapping = PHASE_MAPPINGS[mode]
    cluster_mapping = CLUSTERING_PHASE_MAPPING.get(mode, {})
    by_hour = {row['hour_utc'].hour: row for row in metering}
    phases: List[Dict] = []
    for spec in mapping:
        m = by_hour.get(spec['hour_utc'], {'compute': 0.0, 'cloud': 0.0, 'total': 0.0})
        phases.append({
            'hour_utc':       spec['hour_utc'],
            'fr_window':      spec['fr'],
            'phase':          spec['phase'],
            'cr_warehouse':   round(m['total'], 4),
            'cr_compute':     round(m['compute'], 4),
            'cr_cloud':       round(m['cloud'], 4),
            'cr_clustering':  0.0,
            'clustering_tables': [],
        })

    phase_index = {p['phase']: p for p in phases}
    for ac in clustering:
        target_phase = cluster_mapping.get(ac['table_name'])
        if target_phase and target_phase in phase_index:
            phase_index[target_phase]['cr_clustering'] += round(ac['credits'], 4)
            phase_index[target_phase]['clustering_tables'].append(ac['table_name'])

    for p in phases:
        p['cr_total'] = round(p['cr_warehouse'] + p['cr_clustering'], 4)
    return phases


def compute_totals(phases: List[Dict], tarif: float) -> Dict:
    """Sommes globales et conversion € selon le tarif Mediprix.

    Note : ``eur_same_mode_monthly_*`` projettent le coût en supposant TOUTES les
    nuits du mois identiques au mode mesuré ; c'est utile uniquement pour comparer
    deux nuits du même mode entre elles. Pour le coût mensuel réel hybride, voir
    la note dans :func:`render_text` qui pondère full + incremental + skip.
    """
    cr_warehouse  = round(sum(p['cr_warehouse']  for p in phases), 4)
    cr_clustering = round(sum(p['cr_clustering'] for p in phases), 4)
    cr_total      = round(cr_warehouse + cr_clustering, 4)
    return {
        'cr_warehouse':                 cr_warehouse,
        'cr_clustering':                cr_clustering,
        'cr_total':                     cr_total,
        'eur_total':                    round(cr_total * tarif, 4),
        'eur_same_mode_monthly_skip':   round(cr_total * 26 * tarif, 2),
        'eur_same_mode_monthly_full':   round(cr_total * 30 * tarif, 2),
    }


def render_text(date_anchor: date, phases: List[Dict], totals: Dict, tarif: float, mode: str) -> str:
    """Format texte box-drawing pour console + fichier markdown."""
    weekday_fr = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'][date_anchor.weekday()]
    lines = []
    lines.append(f'Rapport coût Snowflake — nuit du {weekday_fr} {date_anchor.isoformat()} (UTC) — mode {mode.upper()}')
    lines.append(f'Warehouse : {WAREHOUSE_NAME}    Tarif : {tarif:.4f} €/crédit')
    lines.append('')
    lines.append('┌────────────┬────────────────┬─────────────────────────────────────────────────────────┬──────────────┬──────────────┬────────────┬──────────┐')
    lines.append('│ Heure UTC  │   Heure FR     │ Phase                                                   │ cr warehouse │ cr clustering│ cr total   │  EUR     │')
    lines.append('├────────────┼────────────────┼─────────────────────────────────────────────────────────┼──────────────┼──────────────┼────────────┼──────────┤')
    for p in phases:
        lines.append(
            '│ {hr:02d}:00       │ {fr:<14} │ {phase:<55} │ {cw:>12.4f} │ {cc:>12.4f} │ {ct:>10.4f} │ {eur:>7.3f}€ │'.format(
                hr=p['hour_utc'], fr=p['fr_window'], phase=p['phase'][:55],
                cw=p['cr_warehouse'], cc=p['cr_clustering'], ct=p['cr_total'],
                eur=p['cr_total'] * tarif,
            )
        )
    lines.append('├────────────┴────────────────┴─────────────────────────────────────────────────────────┼──────────────┼──────────────┼────────────┼──────────┤')
    lines.append(
        '│ TOTAL                                                                                  │ {cw:>12.4f} │ {cc:>12.4f} │ {ct:>10.4f} │ {eur:>7.3f}€ │'.format(
            cw=totals['cr_warehouse'], cc=totals['cr_clustering'],
            ct=totals['cr_total'], eur=totals['eur_total'],
        )
    )
    lines.append('└────────────────────────────────────────────────────────────────────────────────────────┴──────────────┴──────────────┴────────────┴──────────┘')
    lines.append('')
    lines.append(f"Projection si toutes les nuits étaient en mode {mode.upper()} :")
    lines.append(f"  - 26 nuits (skip dimanche) : {totals['eur_same_mode_monthly_skip']:.2f} €")
    lines.append(f"  - 30 nuits (sans skip)     : {totals['eur_same_mode_monthly_full']:.2f} €")
    lines.append('')
    lines.append('NOTE : ces projections supposent un mois mono-mode (irréaliste).')
    lines.append('Pour le coût mensuel réel hybride, mesurer les 3 modes et pondérer')
    lines.append('avec ~4,33 lundis (full) + ~21,67 mar-sam (incremental) + ~4,33 dim (skip).')
    return '\n'.join(lines)


def parse_args() -> argparse.Namespace:
    """CLI parsing."""
    parser = argparse.ArgumentParser(description='Rapport coût Snowflake nuit MediCore')
    parser.add_argument('--date', type=str, default=None,
                        help='Date de démarrage (YYYY-MM-DD UTC). Défaut : avant-hier (latence ACCOUNT_USAGE)')
    parser.add_argument('--tarif', type=float, default=DEFAULT_TARIF_EUR_PER_CREDIT,
                        help=f'Tarif €/crédit (défaut {DEFAULT_TARIF_EUR_PER_CREDIT})')
    parser.add_argument('--mode', choices=['auto', 'full', 'incremental', 'skip'], default='auto',
                        help='Mode du ref_reload (auto = détection par jour de la semaine)')
    parser.add_argument('--json', action='store_true', help='Sortie JSON au lieu du tableau')
    parser.add_argument('--markdown', type=str, default=None,
                        help='Chemin de sauvegarde markdown du rapport')
    return parser.parse_args()


def resolve_mode(arg_mode: str, date_anchor: date) -> str:
    """Détermine le mode (full/incremental/skip) depuis --mode ou par auto-détection.

    Args:
        arg_mode: Valeur passée via CLI ('auto', 'full', 'incremental', 'skip').
        date_anchor: Jour de démarrage du run nocturne (UTC).

    Returns:
        Mode résolu parmi 'full', 'incremental', 'skip'.
    """
    if arg_mode != 'auto':
        return arg_mode
    return MODE_BY_WEEKDAY[date_anchor.weekday()]


def resolve_anchor(arg_date: Optional[str]) -> date:
    """Parse --date ou défaut J-2 (latence ACCOUNT_USAGE 45 min - 3 h)."""
    if arg_date:
        return date.fromisoformat(arg_date)
    return date.today() - timedelta(days=2)


def run(date_anchor: date, tarif: float, mode: str) -> Dict:
    """Pipeline principal : fetch + agrégation + totaux selon le mode.

    Args:
        date_anchor: Jour de démarrage (UTC) du traitement de nuit à analyser.
        tarif: Tarif €/crédit Mediprix.
        mode: 'full', 'incremental' ou 'skip'.

    Returns:
        Dict {date, mode, phases, totals, tarif, warehouse}.
    """
    start_utc = datetime(date_anchor.year, date_anchor.month, date_anchor.day, 18, 0, 0)
    end_utc = start_utc + timedelta(hours=10)
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER SESSION SET TIMEZONE = 'UTC'")
        metering = fetch_metering(cur, start_utc, end_utc, WAREHOUSE_NAME)
        clustering = fetch_clustering(cur, start_utc, end_utc)
    finally:
        cur.close()
        conn.close()
    phases = build_phases(metering, clustering, mode)
    totals = compute_totals(phases, tarif)
    return {
        'date_anchor': date_anchor.isoformat(),
        'weekday':     date_anchor.strftime('%A').lower(),
        'mode':        mode,
        'window_utc':  [start_utc.isoformat(), end_utc.isoformat()],
        'warehouse':   WAREHOUSE_NAME,
        'tarif_eur_per_credit': tarif,
        'phases':      phases,
        'totals':      totals,
    }


def main() -> int:
    args = parse_args()
    date_anchor = resolve_anchor(args.date)
    mode = resolve_mode(args.mode, date_anchor)
    try:
        report = run(date_anchor, args.tarif, mode)
    except Exception as e:
        logger.exception('snowflake_cost_report.py : échec %s', e)
        return 2

    if args.json:
        print(json.dumps(report, default=str, indent=2, ensure_ascii=False))
    else:
        text = render_text(date_anchor, report['phases'], report['totals'], args.tarif, mode)
        print(text)

    if args.markdown:
        target = Path(args.markdown)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = render_text(date_anchor, report['phases'], report['totals'], args.tarif, mode)
        target.write_text(text, encoding='utf-8')
        logger.info('Rapport sauvegardé : %s', target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
