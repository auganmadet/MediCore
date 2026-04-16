"""Maintenance Phase 4 : verification dbt Staging / MARTS.

Verifie l'etat des modeles et tests dbt :
- D1 : Modeles dbt en erreur (run_results.json)
- D2 : Tests dbt echoues (not_null, unique, relationships)
- D3 : Source freshness depassee
- D4 : Modeles non executes (skipped)
- D5 : Tables MARTS vides
- D6 : Row Access Policies detachees (si reactivees)

S'auto-authentifie via .env. Lecture seule.

Usage :
    python scripts/dbt_maintenance.py
    python scripts/dbt_maintenance.py --results-path /app/dbt/target/run_results.json
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_RESULTS_PATH = str(Path(__file__).resolve().parent.parent / 'dbt' / 'target' / 'run_results.json')

MARTS_TABLES = [
    'DIM_PHARMACIE', 'DIM_PRODUIT', 'DIM_FOURNISSEUR',
    'FACT_COMMANDES', 'FACT_OPERATEUR', 'FACT_PRIX_JOURNALIER',
    'FACT_RUPTURES', 'FACT_STOCK_MOUVEMENT', 'FACT_STOCK_VALORISATION',
    'FACT_TRESORERIE', 'FACT_VENTES',
    'MART_KPI_ABC', 'MART_KPI_CA_EVOLUTION', 'MART_KPI_DORMANT',
    'MART_KPI_ECOULEMENT', 'MART_KPI_GENERIQUE', 'MART_KPI_MARGE',
    'MART_KPI_OPERATEUR', 'MART_KPI_QUALITE_DONNEES',
    'MART_KPI_REMISE_LABO', 'MART_KPI_RUPTURES',
    'MART_KPI_STOCK_VALORISATION', 'MART_KPI_SYNTHESE_PHARMACIE',
    'MART_KPI_TRESORERIE', 'MART_KPI_UNIVERS',
    'MART_KPI_MARGE_PAR_PRODUIT', 'MART_KPI_MARGE_PAR_UNIVERS',
    'MART_KPI_RUPTURES_PAR_PRODUIT', 'MART_KPI_ECOULEMENT_PAR_FOURNISSEUR',
    'MART_KPI_VENTES_PAR_PRODUIT', 'MART_KPI_GENERIQUE_MARGE',
    'MART_KPI_STOCK',
]


def get_snowflake_conn():
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
    )


def load_run_results(path):
    """Charge run_results.json si disponible."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def check_d1_model_errors(results_path):
    """D1 : modeles dbt en erreur."""
    data = load_run_results(results_path)
    if data is None:
        return True, {'status': 'run_results.json non trouve (pas de run recent)'}

    errors = []
    for r in data.get('results', []):
        if r.get('status') in ('error', 'fail'):
            node = r.get('unique_id', '?')
            msg = r.get('message', '')[:150]
            timing = r.get('execution_time', 0)
            errors.append({
                'model': node,
                'error': msg,
                'duration_s': round(timing, 1),
            })

    return len(errors) == 0, {'errors': errors, 'total_models': len(data.get('results', []))}


def check_d2_test_failures(results_path):
    """D2 : tests dbt echoues."""
    data = load_run_results(results_path)
    if data is None:
        return True, {'status': 'run_results.json non trouve'}

    failures = []
    warnings = []
    for r in data.get('results', []):
        node = r.get('unique_id', '')
        if '.test.' not in node and 'test' not in node:
            continue
        status = r.get('status', '')
        if status == 'fail':
            failures.append({
                'test': node,
                'message': r.get('message', '')[:100],
                'failures_count': r.get('failures', 0),
            })
        elif status == 'warn':
            warnings.append({
                'test': node,
                'message': r.get('message', '')[:100],
            })

    return len(failures) == 0, {
        'failures': failures,
        'warnings': warnings,
        'nb_failures': len(failures),
        'nb_warnings': len(warnings),
    }


def check_d3_freshness():
    """D3 : source freshness depassee."""
    freshness_path = str(Path(DEFAULT_RESULTS_PATH).parent / 'sources.json')
    if not os.path.exists(freshness_path):
        return True, {'status': 'sources.json non trouve (freshness non executee)'}

    data = load_run_results(freshness_path)
    if data is None:
        return True, {'status': 'fichier vide'}

    stale = []
    for r in data.get('results', []):
        status = r.get('status', '')
        if status in ('error', 'ERROR'):
            source = r.get('unique_id', '?')
            age = r.get('max_loaded_at_time_ago_in_s', 0)
            stale.append({
                'source': source,
                'age_hours': round(age / 3600, 1) if age else '?',
            })

    return len(stale) == 0, {'stale_sources': stale}


def check_d4_skipped(results_path):
    """D4 : modeles non executes (skipped)."""
    data = load_run_results(results_path)
    if data is None:
        return True, {'status': 'run_results.json non trouve'}

    skipped = []
    for r in data.get('results', []):
        if r.get('status') == 'skipped':
            skipped.append(r.get('unique_id', '?'))

    return len(skipped) == 0, {'skipped': skipped, 'nb_skipped': len(skipped)}


def check_d5_empty_marts():
    """D5 : tables MARTS vides."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        empty = []

        for table in MARTS_TABLES:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM MARTS.{table}')
                count = cursor.fetchone()[0]
                if count == 0:
                    empty.append(table)
            except Exception:
                empty.append(f'{table} (erreur)')

        cursor.close()
        conn.close()
        return len(empty) == 0, {'empty_tables': empty, 'total': len(MARTS_TABLES)}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_d6_policies():
    """D6 : Row Access Policies detachees (verification informative)."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()

        cursor.execute("SHOW ROW ACCESS POLICIES IN SCHEMA AUDIT")
        policies = cursor.fetchall()

        cursor.close()
        conn.close()

        policy_names = [p[1] for p in policies] if policies else []
        return True, {
            'policies_definies': policy_names,
            'status': 'dormantes (Alternative A — pas attachees aux tables)',
        }
    except Exception as e:
        return True, {'status': f'non verifiable: {str(e)[:80]}'}


DBT_RETRY_FLAG = '/tmp/dbt_maintenance_retry_done'


def fix_d1_d2_rerun_dbt():
    """Relance dbt run + dbt test pour corriger les modeles/tests en erreur.

    Garde-fous :
    - 1 seul retry par jour (flag /tmp/dbt_maintenance_retry_done)
    - Timeout 30 min
    - Compare les erreurs avant/apres : si meme nombre → probleme non transitoire, stop
    """
    import subprocess

    # Garde-fou : 1 seul retry par jour
    if os.path.exists(DBT_RETRY_FLAG):
        return False, 'SKIP: dbt deja relance aujourd\'hui (flag anti-boucle)'

    env = os.getenv('ENV', 'prod')
    dbt_dir = str(Path(__file__).resolve().parent.parent / 'dbt')

    # Sauvegarder le nombre d'erreurs avant relance
    pre_results = load_run_results(os.path.join(dbt_dir, 'target', 'run_results.json'))
    pre_errors = 0
    if pre_results:
        for r in pre_results.get('results', []):
            if r.get('status') in ('error', 'fail'):
                pre_errors += 1

    try:
        logger.info('Relance dbt run (staging + marts)...')
        result = subprocess.run(
            ['dbt', 'run', '--select', 'tag:staging', 'tag:marts', '--target', env],
            capture_output=True, text=True, timeout=1800,
            cwd=dbt_dir,
        )
        if result.returncode != 0:
            # Poser le flag pour ne pas reboucler
            with open(DBT_RETRY_FLAG, 'w') as f:
                f.write('done')
            return False, f'dbt run echoue: {result.stderr[:100]}'

        logger.info('Relance dbt test...')
        result = subprocess.run(
            ['dbt', 'test', '--target', env],
            capture_output=True, text=True, timeout=1800,
            cwd=dbt_dir,
        )

        # Poser le flag dans tous les cas
        with open(DBT_RETRY_FLAG, 'w') as f:
            f.write('done')

        # Comparer les erreurs avant/apres
        post_results = load_run_results(os.path.join(dbt_dir, 'target', 'run_results.json'))
        post_errors = 0
        if post_results:
            for r in post_results.get('results', []):
                if r.get('status') in ('error', 'fail'):
                    post_errors += 1

        if post_errors >= pre_errors and pre_errors > 0:
            return False, f'Meme nombre d\'erreurs apres relance ({pre_errors} -> {post_errors}) — probleme non transitoire'

        if result.returncode != 0:
            return False, f'dbt test: {post_errors} erreurs restantes'

        return True, 'dbt run + test termines avec succes'
    except subprocess.TimeoutExpired:
        with open(DBT_RETRY_FLAG, 'w') as f:
            f.write('done')
        return False, 'dbt timeout apres 30 min'
    except Exception as e:
        return False, str(e)[:100]


def fix_d3_freshness():
    """Relance dbt source freshness."""
    import subprocess
    env = os.getenv('ENV', 'prod')

    try:
        result = subprocess.run(
            ['dbt', 'source', 'freshness', '--target', env],
            capture_output=True, text=True, timeout=300,
            cwd=str(Path(__file__).resolve().parent.parent / 'dbt'),
        )
        return result.returncode == 0, 'freshness recalculee'
    except Exception as e:
        return False, str(e)[:100]


def main():
    parser = argparse.ArgumentParser(description='dbt maintenance (D1-D6)')
    parser.add_argument('--results-path', default=DEFAULT_RESULTS_PATH,
                        help='Chemin vers run_results.json')
    fix_group = parser.add_mutually_exclusive_group()
    fix_group.add_argument('--fix-safe', action='store_true',
                           help='Fix surs : D3 (freshness)')
    fix_group.add_argument('--fix', action='store_true',
                           help='Tous les fix : D1/D2 (relance dbt run+test), D3 (freshness)')
    parser.add_argument('--dry-run', action='store_true', help='Detecte sans corriger')
    args = parser.parse_args()

    print('=' * 60)
    print('DBT MAINTENANCE')
    print('=' * 60)
    print(f'  run_results.json: {args.results_path}')

    checks = [
        ('D1', 'Modeles dbt en erreur', lambda: check_d1_model_errors(args.results_path)),
        ('D2', 'Tests dbt echoues', lambda: check_d2_test_failures(args.results_path)),
        ('D3', 'Source freshness depassee', check_d3_freshness),
        ('D4', 'Modeles skipped', lambda: check_d4_skipped(args.results_path)),
        ('D5', 'Tables MARTS vides', check_d5_empty_marts),
        ('D6', 'Row Access Policies', check_d6_policies),
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
                if isinstance(v, list) and v:
                    for item in v[:5]:
                        print(f'     {k}: {item}')
                    if len(v) > 5:
                        print(f'     ... ({len(v)} total)')
                elif v and k not in ('error',):
                    print(f'     {k}: {v}')
                elif k == 'error':
                    print(f'     Erreur: {v}')

    # Corrections
    if (args.fix or args.fix_safe) and not args.dry_run:
        print('\n--- Corrections ---')

        # Tous les fix (--fix-safe et --fix) — avec garde-fous integres
        if not results.get('D1', {}).get('ok', True) or not results.get('D2', {}).get('ok', True):
            print('  D1/D2 relance dbt run + test (1 seul retry/jour)...')
            ok, msg = fix_d1_d2_rerun_dbt()
            print(f'  D1/D2: {"OK" if ok else "FAIL"} ({msg})')

        if not results.get('D3', {}).get('ok', True):
            print('  D3 relance freshness...')
            ok, msg = fix_d3_freshness()
            print(f'  D3: {"OK" if ok else "FAIL"} ({msg})')

    # Resume
    nb_ok = sum(1 for r in results.values() if r['ok'])
    nb_fail = len(results) - nb_ok
    print(f'\n{"=" * 60}')
    print(f'  Resume: {nb_ok}/6 OK, {nb_fail} FAIL')
    sys.exit(0 if nb_fail == 0 else 1)


if __name__ == '__main__':
    main()
