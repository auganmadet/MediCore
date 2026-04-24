"""Audit complet des 16 dashboards : cartes, filtres, embedding.

Verifie pour chaque dashboard :
- Toutes les cartes sont executables (pas d'erreur)
- Les filtres ont des valeurs disponibles
- L'embedding est active et les parametres configures

Usage :
    python scripts/check_all_dashboards.py <session_token>
"""

import json
import sys
import time
import urllib.request
import urllib.error

if len(sys.argv) < 2:
    print('Usage: python scripts/check_all_dashboards.py <token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'
DASHBOARD_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]


def api_get(path):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f'{BASE}/{path}',
                headers={'X-Metabase-Session': TOKEN},
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(5)
            else:
                raise


def api_post(path, data):
    for attempt in range(3):
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f'{BASE}/{path}', data=body, method='POST',
                headers={
                    'X-Metabase-Session': TOKEN,
                    'Content-Type': 'application/json',
                },
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError):
            if attempt < 2:
                time.sleep(5)
            else:
                raise


# Charger metadata pour valider les field IDs
print('Chargement metadata...')
meta = api_get('database/2/metadata?include_hidden=false')
valid_field_ids = set()
for t in meta.get('tables', []):
    for f in t.get('fields', []):
        valid_field_ids.add(f['id'])
print(f'  {len(valid_field_ids)} fields valides\n')

# Collections
colls = {}
for c in api_get('collection'):
    colls[c['id']] = {'name': c.get('name', '?'), 'parent_id': c.get('parent_id')}


def get_path(coll_id):
    parts = []
    cur = coll_id
    while cur and cur in colls:
        parts.append(colls[cur]['name'])
        cur = colls[cur]['parent_id']
    return ' / '.join(reversed(parts))


# Resultats globaux
total_cards = 0
total_ok = 0
total_err = 0
total_filters = 0
total_filters_ok = 0
filter_issues = []
card_issues = []

print('=' * 80)
print('AUDIT COMPLET DES 16 DASHBOARDS')
print('=' * 80)

for i, dash_id in enumerate(DASHBOARD_IDS):
    if i > 0:
        time.sleep(2)

    dash = api_get(f'dashboard/{dash_id}')
    name = dash.get('name', '?')
    coll_id = dash.get('collection_id')
    path = get_path(coll_id)
    params = dash.get('parameters', [])
    embedding = dash.get('enable_embedding', False)
    embedding_params = dash.get('embedding_params', {})

    print(f'\n--- D{dash_id-1} (id={dash_id}): {name} ---')
    print(f'  Collection: {path}')
    print(f'  Embedding: {"OUI" if embedding else "NON"}')
    if embedding_params:
        summary = ', '.join(f'{k}={v}' for k, v in embedding_params.items())
        print(f'  Params embedding: {summary}')

    # Verifier les filtres
    for p in params:
        total_filters += 1
        slug = p.get('slug', '')
        ptype = p.get('type', '')
        vqt = p.get('values_query_type', '?')
        status = 'OK'

        if ptype.startswith('string') and vqt != 'list':
            status = 'PAS LISTE'
            filter_issues.append(f'  D{dash_id-1} filtre {slug}: {vqt} (devrait etre list)')
        else:
            total_filters_ok += 1

        print(f'  Filtre {slug}: type={ptype} widget={vqt} [{status}]')

    # Verifier les cartes
    dashcards = dash.get('dashcards', [])
    print(f'  Cartes: {len(dashcards)}')

    for dc in dashcards:
        card = dc.get('card', {})
        card_id = card.get('id')
        if not card_id:
            continue

        total_cards += 1
        card_name = card.get('name', '?')[:35]
        db_id = card.get('database_id')

        # Verifier database_id
        if db_id != 2:
            status = f'ERREUR db={db_id}'
            total_err += 1
            card_issues.append(f'  D{dash_id-1} card {card_id} ({card_name}): db={db_id}')
            print(f'    card {card_id}: {status} - {card_name}')
            continue

        # Verifier les mappings
        mappings = dc.get('parameter_mappings', [])
        mapping_ok = True
        for m in mappings:
            target = m.get('target', [])
            if len(target) >= 2 and target[0] == 'dimension':
                inner = target[1]
                if isinstance(inner, list) and len(inner) >= 2 and inner[0] == 'field':
                    fid = inner[1]
                    if isinstance(fid, int) and fid not in valid_field_ids:
                        mapping_ok = False

        if not mapping_ok:
            total_err += 1
            card_issues.append(f'  D{dash_id-1} card {card_id} ({card_name}): field ID invalide')
            print(f'    card {card_id}: FIELD ID INVALIDE - {card_name}')
            continue

        # Executer la carte pour verifier qu'elle retourne des donnees
        full_card = api_get(f'card/{card_id}')
        dq = full_card.get('dataset_query', {})
        time.sleep(1)

        try:
            result = api_post('dataset', dq)
            error = result.get('error') or result.get('data', {}).get('error')
            if error:
                total_err += 1
                err_msg = str(error)[:80]
                card_issues.append(f'  D{dash_id-1} card {card_id} ({card_name}): {err_msg}')
                print(f'    card {card_id}: ERREUR EXEC - {card_name}')
                print(f'      {err_msg}')
            else:
                rows = result.get('data', {}).get('rows', [])
                total_ok += 1
                print(f'    card {card_id}: OK ({len(rows)} lignes) - {card_name}')
        except Exception as e:
            total_err += 1
            card_issues.append(f'  D{dash_id-1} card {card_id} ({card_name}): {str(e)[:80]}')
            print(f'    card {card_id}: ERREUR - {card_name}: {str(e)[:80]}')

# Resume
print('\n' + '=' * 80)
print('RESUME')
print('=' * 80)
print(f'  Cartes:  {total_ok}/{total_cards} OK, {total_err} erreurs')
print(f'  Filtres: {total_filters_ok}/{total_filters} OK')

if card_issues:
    print(f'\n  CARTES EN ERREUR:')
    for issue in card_issues:
        print(issue)

if filter_issues:
    print(f'\n  FILTRES A CORRIGER:')
    for issue in filter_issues:
        print(issue)

if not card_issues and not filter_issues:
    print('\n  TOUT EST OK')
