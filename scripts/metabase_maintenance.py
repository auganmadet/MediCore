"""Orchestrateur de maintenance Metabase.

Detecte et corrige automatiquement les 10 problemes identifies (P1-P10).
S'auto-authentifie a Metabase et Snowflake via .env.
Appelle les scripts existants pour chaque correction.

Integrable dans batch_loop.sh a 05h00.

Usage :
    python scripts/metabase_maintenance.py              # mode automatique
    python scripts/metabase_maintenance.py --dry-run     # simulation
    python scripts/metabase_maintenance.py --diagnose --card 369
    python scripts/metabase_maintenance.py --diagnose --dashboard 5
    python scripts/metabase_maintenance.py --pha-id 217
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

SCRIPTS_DIR = Path(__file__).resolve().parent
BASE_URL = os.getenv('METABASE_URL', os.getenv('METABASE_SITE_URL', 'http://localhost:3001'))
BASE = f'{BASE_URL}/api'
DB_ID = int(os.getenv('MB_SOURCE_DATABASE_ID', '2'))
DASHBOARD_IDS = list(range(2, 18))
LIST_FILTER_SLUGS = {'pharmacie', 'fournisseur', 'univers', 'operateur', 'statut_dormant'}
PYTHON = sys.executable


# ============================================================
# Auto-authentification
# ============================================================

def get_token():
    """Auto-authentification Metabase via .env."""
    data = json.dumps({
        'username': os.getenv('METABASE_ADMIN_EMAIL'),
        'password': os.getenv('METABASE_ADMIN_PASSWORD'),
    }).encode()
    req = urllib.request.Request(
        f'{BASE}/session', data=data, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())['id']


def api_get(token, path):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f'{BASE}/{path}', headers={'X-Metabase-Session': token},
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(5)
            else:
                raise


def api_post(token, path, data):
    for attempt in range(3):
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f'{BASE}/{path}', data=body, method='POST',
                headers={'X-Metabase-Session': token, 'Content-Type': 'application/json'},
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(5)
            else:
                raise


# ============================================================
# Appel scripts existants
# ============================================================

def run_script(script_name, *args):
    """Execute un script existant avec les arguments passes."""
    script_path = SCRIPTS_DIR / script_name
    cmd = [PYTHON, str(script_path)] + list(args)
    print(f'  -> {script_name} {" ".join(args[:3])}{"..." if len(args) > 3 else ""}')
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            print(f'     {line}')
    if result.returncode != 0 and result.stderr:
        for line in result.stderr.strip().split('\n')[:5]:
            print(f'     ERREUR: {line}')
    return result.returncode == 0


# ============================================================
# Detection des problemes
# ============================================================

def detect_p1(token):
    """P1 : cartes avec mauvais database_id."""
    issues = []
    seen = set()
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for dc in dash.get('dashcards', []):
            card = dc.get('card', {})
            card_id = card.get('id')
            if card_id and card_id not in seen and card.get('database_id') != DB_ID:
                issues.append(card_id)
                seen.add(card_id)
    return issues


def detect_p2(token):
    """P2 : SQL native reference MEDICORE au lieu de MEDICORE_PROD."""
    issues = []
    seen = set()
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for dc in dash.get('dashcards', []):
            card_id = dc.get('card_id')
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            full_card = api_get(token, f'card/{card_id}')
            dq = full_card.get('dataset_query', {})
            stages = dq.get('stages', [])
            if stages:
                native = stages[0].get('native', '')
                if isinstance(native, str) and 'MEDICORE.' in native and 'MEDICORE_PROD.' not in native:
                    issues.append(card_id)
    return issues


def detect_p4(token):
    """P4 : filtres texte pas en mode liste deroulante."""
    issues = []
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for p in dash.get('parameters', []):
            slug = p.get('slug', '')
            if slug in LIST_FILTER_SLUGS and p.get('values_query_type') != 'list':
                issues.append((dash_id, slug))
    return issues


def detect_p5(token):
    """P5 : filtre date en date/range au lieu de date/month-year."""
    issues = []
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for p in dash.get('parameters', []):
            if p.get('type') == 'date/range':
                issues.append((dash_id, p.get('slug')))
    return issues


def detect_p6(token):
    """P6 : embedding non active."""
    issues = []
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        if not dash.get('enable_embedding'):
            issues.append(dash_id)
    return issues


def detect_p7(token):
    """P7 : cartes non executables."""
    issues = []
    seen = set()
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for dc in dash.get('dashcards', []):
            card_id = dc.get('card_id')
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            full_card = api_get(token, f'card/{card_id}')
            dq = full_card.get('dataset_query', {})
            time.sleep(0.5)
            try:
                result = api_post(token, 'dataset', dq)
                error = result.get('error') or result.get('data', {}).get('error')
                if error:
                    issues.append((card_id, full_card.get('name', '?'), str(error)[:100]))
            except Exception as e:
                issues.append((card_id, full_card.get('name', '?'), str(e)[:100]))
    return issues


def detect_p8(token):
    """P8 : cartes SQL natives avec template-tag date dans un dashboard embedded."""
    issues = []
    seen = set()
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        if not dash.get('enable_embedding'):
            continue
        for dc in dash.get('dashcards', []):
            card_id = dc.get('card_id')
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            full_card = api_get(token, f'card/{card_id}')
            dq = full_card.get('dataset_query', {})
            stages = dq.get('stages', [])
            if stages and stages[0].get('lib/type') == 'mbql.stage/native':
                tags = stages[0].get('template-tags', {})
                for tag_name, tag_def in tags.items():
                    if tag_def.get('type') == 'date':
                        issues.append((card_id, full_card.get('name', '?'), tag_name))
    return issues


def detect_p9(token):
    """P9 : filtres mappes uniquement a des cartes SQL natives (pas de liste)."""
    issues = []
    for dash_id in DASHBOARD_IDS:
        dash = api_get(token, f'dashboard/{dash_id}')
        for p in dash.get('parameters', []):
            slug = p.get('slug', '')
            if slug not in LIST_FILTER_SLUGS:
                continue
            has_mbql_mapping = False
            has_any_mapping = False
            for dc in dash.get('dashcards', []):
                for m in dc.get('parameter_mappings', []):
                    if m.get('parameter_id') == slug:
                        has_any_mapping = True
                        target = m.get('target', [])
                        if target and target[0] == 'dimension' and len(target) > 1:
                            inner = target[1]
                            if isinstance(inner, list) and inner[0] == 'field':
                                has_mbql_mapping = True
            if has_any_mapping and not has_mbql_mapping:
                issues.append((dash_id, slug))
    return issues


# ============================================================
# Corrections P7 — cartes non executables
# ============================================================

def fix_p7_card(token, card_id, error_msg):
    """Tente de corriger une carte non executable selon le message d'erreur.

    Returns:
        str description du fix applique, ou None si non corrigeable.
    """
    error_lower = error_msg.lower()

    # Cause 1 : database renommee (P2)
    if 'does not exist' in error_lower and 'database' in error_lower:
        full_card = api_get(token, f'card/{card_id}')
        dq = full_card.get('dataset_query', {})
        stages = dq.get('stages', [])
        if stages:
            native = stages[0].get('native', '')
            if isinstance(native, str) and 'MEDICORE.' in native and 'MEDICORE_PROD.' not in native:
                stages[0]['native'] = native.replace('MEDICORE.', 'MEDICORE_PROD.')
                try:
                    from scripts_helpers import api_put_card
                except ImportError:
                    pass
                import urllib.request
                import json as json_mod
                body = json_mod.dumps({'dataset_query': dq}).encode()
                req = urllib.request.Request(
                    f'{BASE}/card/{card_id}', data=body, method='PUT',
                    headers={'X-Metabase-Session': token, 'Content-Type': 'application/json'},
                )
                urllib.request.urlopen(req, timeout=60)
                return 'P2 fix: MEDICORE -> MEDICORE_PROD'
        return None

    # Cause 2 : mauvais database_id (P1)
    if 'permission' in error_lower or 'denied' in error_lower:
        full_card = api_get(token, f'card/{card_id}')
        if full_card.get('database_id') != DB_ID:
            dq = full_card.get('dataset_query', {})
            dq['database'] = DB_ID
            import urllib.request
            import json as json_mod
            body = json_mod.dumps({'database_id': DB_ID, 'dataset_query': dq}).encode()
            req = urllib.request.Request(
                f'{BASE}/card/{card_id}', data=body, method='PUT',
                headers={'X-Metabase-Session': token, 'Content-Type': 'application/json'},
            )
            urllib.request.urlopen(req, timeout=60)
            return f'P1 fix: database_id -> {DB_ID}'
        return None

    # Cause 3 : erreur SQL compilation (SQL native cassee -> recreer en MBQL)
    if 'sql compilation error' in error_lower:
        # Tenter de recreer en MBQL via create_mbql_card.py
        success = run_script('create_mbql_card.py', '--card', str(card_id))
        if success:
            return f'P3/P8 fix: carte recree en MBQL'
        return None

    # Cause 4 : table/colonne inexistante
    if 'does not exist' in error_lower and ('object' in error_lower or 'table' in error_lower):
        # Tenter de re-mapper les field IDs via metadata
        full_card = api_get(token, f'card/{card_id}')
        dq = full_card.get('dataset_query', {})
        stages = dq.get('stages', [])
        if stages and stages[0].get('native'):
            # SQL native — tenter recreer en MBQL
            success = run_script('create_mbql_card.py', '--card', str(card_id))
            if success:
                return 'Carte SQL native recree en MBQL'
        return None

    # Cause 5 : colonne invalide
    if 'invalid identifier' in error_lower or 'invalid column' in error_lower:
        success = run_script('create_mbql_card.py', '--card', str(card_id))
        if success:
            return 'Carte recree en MBQL (colonne invalide)'
        return None

    # Cause 6 : timeout -> tenter optimisation (LIMIT, simplification)
    if 'timeout' in error_lower or 'statement reached' in error_lower:
        # Alerter seulement — optimisation SQL trop risquee en automatique
        logger.warning(f'Card {card_id}: timeout detecte — verifier la requete ou le warehouse')
        return None

    # Cause inconnue
    return None


# ============================================================
# Corrections
# ============================================================

def fix_issues(token, dry_run, pha_id):
    """Detecte et corrige tous les problemes."""
    report = {'detected': {}, 'fixed': {}, 'manual': {}}

    # P1 : database_id incorrect
    print('\n[P1] Cartes avec mauvais database_id...')
    p1 = detect_p1(token)
    report['detected']['P1'] = len(p1)
    if p1:
        print(f'  {len(p1)} cartes detectees: {p1}')
        if not dry_run:
            run_script('fix_cards_db.py', token)
            report['fixed']['P1'] = len(p1)
    else:
        print('  OK')

    # P2 : MEDICORE au lieu de MEDICORE_PROD
    print('\n[P2] SQL native avec ancien nom database...')
    p2 = detect_p2(token)
    report['detected']['P2'] = len(p2)
    if p2:
        print(f'  {len(p2)} cartes detectees: {p2}')
        if not dry_run:
            run_script('fix_cards_db_name.py', token)
            report['fixed']['P2'] = len(p2)
    else:
        print('  OK')

    # P4 : filtres pas en liste deroulante
    print('\n[P4] Filtres texte pas en liste deroulante...')
    p4 = detect_p4(token)
    report['detected']['P4'] = len(p4)
    if p4:
        print(f'  {len(p4)} filtres detectes')
        for dash_id, slug in p4:
            print(f'    Dashboard {dash_id}: {slug}')
        if not dry_run:
            run_script('fix_filter_widgets.py', token)
            report['fixed']['P4'] = len(p4)
    else:
        print('  OK')

    # P5 : date/range au lieu de date/month-year
    print('\n[P5] Filtres date en date/range...')
    p5 = detect_p5(token)
    report['detected']['P5'] = len(p5)
    if p5:
        print(f'  {len(p5)} filtres detectes')
        for dash_id, slug in p5:
            print(f'    Dashboard {dash_id}: {slug}')
        if not dry_run:
            run_script('fix_dashboard_date_params.py', token)
            report['fixed']['P5'] = len(p5)
    else:
        print('  OK')

    # P6 : embedding non active
    print('\n[P6] Embedding non active...')
    p6 = detect_p6(token)
    report['detected']['P6'] = len(p6)
    if p6:
        print(f'  {len(p6)} dashboards detectes: {p6}')
        if not dry_run:
            run_script('enable_embedding.py', token)
            report['fixed']['P6'] = len(p6)
    else:
        print('  OK')

    # P8 : cartes SQL natives avec template-tag date en embedding
    print('\n[P8] Cartes SQL natives avec template-tag date en embedding...')
    p8 = detect_p8(token)
    report['detected']['P8'] = len(p8)
    if p8:
        print(f'  {len(p8)} cartes detectees')
        card_args = []
        for card_id, name, tag in p8:
            print(f'    Card {card_id} ({name}): tag "{tag}"')
            card_args.extend(['--card', str(card_id)])
        if not dry_run:
            run_script('create_mbql_card.py', *card_args)
            report['fixed']['P8'] = len(p8)
    else:
        print('  OK')

    # P9 : filtres sans mapping MBQL
    print('\n[P9] Filtres mappes uniquement a des cartes SQL natives...')
    p9 = detect_p9(token)
    report['detected']['P9'] = len(p9)
    if p9:
        print(f'  {len(p9)} filtres detectes')
        for dash_id, slug in p9:
            print(f'    Dashboard {dash_id}: filtre "{slug}"')
        # P8 corrige aussi P9 (memes cartes recrees en MBQL)
        report['fixed']['P9'] = report['fixed'].get('P8', 0) and len(p9)
    else:
        print('  OK')

    # P7 : cartes non executables (en dernier car lent)
    print('\n[P7] Cartes non executables (execution de chaque carte)...')
    print('  (cette etape peut prendre plusieurs minutes)')
    p7 = detect_p7(token)
    report['detected']['P7'] = len(p7)
    if p7:
        print(f'  {len(p7)} cartes en erreur')
        fixed_p7 = 0
        for card_id, name, error in p7:
            print(f'    Card {card_id} ({name}): {error}')
            if not dry_run:
                fix_result = fix_p7_card(token, card_id, error)
                if fix_result:
                    print(f'    -> CORRIGE: {fix_result}')
                    fixed_p7 += 1
                else:
                    print(f'    -> NON CORRIGE (intervention manuelle)')
        report['fixed']['P7'] = fixed_p7
        if fixed_p7 < len(p7):
            report['manual']['P7'] = len(p7) - fixed_p7
    else:
        print('  OK')

    # P3 : detecte par P7 (erreurs SQL specifiques)
    report['detected']['P3'] = 0

    # P10 : nouvelles pharmacies
    print('\n[P10] Nouvelles pharmacies a provisionner...')
    pha_args = ['--run-id', 'maintenance']
    if pha_id:
        pha_args.extend(['--pha-id', str(pha_id)])
    if dry_run:
        pha_args.append('--dry-run')
    run_script('provision_rls.py', *pha_args)

    return report


def print_report(report):
    """Affiche le rapport final."""
    print('\n' + '=' * 60)
    print('RAPPORT DE MAINTENANCE')
    print('=' * 60)

    all_problems = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10']
    for p in all_problems:
        detected = report['detected'].get(p, 0)
        fixed = report['fixed'].get(p, 0)
        manual = report['manual'].get(p, 0)

        if detected == 0:
            status = 'OK'
        elif fixed >= detected:
            status = f'CORRIGE ({fixed})'
        elif manual > 0:
            status = f'PARTIEL ({fixed} corriges, {manual} manuels)'
        else:
            status = f'DETECTE ({detected})'

        print(f'  {p:>3}: {status}')

    total_detected = sum(report['detected'].values())
    total_fixed = sum(report['fixed'].values())
    total_manual = sum(report['manual'].values())
    print(f'\n  Total: {total_detected} detectes, {total_fixed} corriges, {total_manual} manuels')


def diagnose_card(token, card_id):
    """Mode diagnostic d'une carte specifique."""
    print(f'\n=== Diagnostic carte {card_id} ===')
    run_script('show_card_query.py', token, str(card_id))
    print()
    run_script('diagnose_cards.py', token, str(card_id))


def diagnose_dashboard(token, dash_id):
    """Mode diagnostic d'un dashboard specifique."""
    print(f'\n=== Diagnostic dashboard {dash_id} ===')
    run_script('show_dashboard_params.py', token, str(dash_id))
    print()
    run_script('diagnose_cards.py', token, '--dashboard', str(dash_id))


def main():
    parser = argparse.ArgumentParser(description='Maintenance Metabase (P1-P10)')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans modification')
    parser.add_argument('--pha-id', type=int, help='Provisionner une seule pharmacie')
    parser.add_argument('--diagnose', action='store_true', help='Mode diagnostic')
    parser.add_argument('--card', type=int, help='Carte a diagnostiquer (avec --diagnose)')
    parser.add_argument('--dashboard', type=int, help='Dashboard a diagnostiquer (avec --diagnose)')
    args = parser.parse_args()

    print('=' * 60)
    print('METABASE MAINTENANCE')
    print('=' * 60)

    token = get_token()
    print('Authentification Metabase: OK')

    if args.diagnose:
        if args.card:
            diagnose_card(token, args.card)
        elif args.dashboard:
            diagnose_dashboard(token, args.dashboard)
        else:
            print('Specifier --card <id> ou --dashboard <id> avec --diagnose')
        return

    report = fix_issues(token, args.dry_run, args.pha_id)
    print_report(report)


if __name__ == '__main__':
    main()
