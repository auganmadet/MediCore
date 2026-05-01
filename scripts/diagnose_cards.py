"""Diagnostique les cartes Metabase en erreur.

Inspecte le dataset_query de chaque carte pour trouver :
- des field IDs qui n'appartiennent pas a database_id=2
- des table IDs invalides
- des erreurs de requete

Usage :
    python scripts/diagnose_cards.py <session_token> <card_id> [card_id ...]
    python scripts/diagnose_cards.py <session_token> --dashboard <dash_id>
"""

import json
import sys
import urllib.request
import urllib.error

if len(sys.argv) < 3:
    print('Usage:')
    print('  python scripts/diagnose_cards.py <token> <card_id> [card_id ...]')
    print('  python scripts/diagnose_cards.py <token> --dashboard <dash_id>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'


def api_get(path):
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def api_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='POST',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json',
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': e.read().decode()[:200], 'status': e.code}


def find_field_ids(obj):
    """Extrait tous les field IDs d'un objet MBQL."""
    ids = []
    if isinstance(obj, list):
        if len(obj) >= 2 and obj[0] == 'field' and isinstance(obj[1], int):
            ids.append(obj[1])
        for item in obj:
            ids.extend(find_field_ids(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            ids.extend(find_field_ids(v))
    return ids


def find_table_ids(obj):
    """Extrait tous les source-table IDs."""
    ids = []
    if isinstance(obj, dict):
        if 'source-table' in obj and isinstance(obj['source-table'], int):
            ids.append(obj['source-table'])
        for v in obj.values():
            ids.extend(find_table_ids(v))
    elif isinstance(obj, list):
        for item in obj:
            ids.extend(find_table_ids(item))
    return ids


# Charger les field/table IDs valides pour database 2
print('Chargement metadata database 2...')
meta = api_get('database/2/metadata?include_hidden=false')
valid_table_ids = set()
valid_field_ids = set()
table_names = {}
field_names = {}

for t in meta.get('tables', []):
    valid_table_ids.add(t['id'])
    table_names[t['id']] = t['name']
    for f in t.get('fields', []):
        valid_field_ids.add(f['id'])
        field_names[f['id']] = f'{t["name"]}.{f["name"]}'

print(f'  {len(valid_table_ids)} tables, {len(valid_field_ids)} fields\n')

# Determiner les card IDs a inspecter
card_ids = []
if '--dashboard' in sys.argv:
    idx = sys.argv.index('--dashboard')
    dash_id = int(sys.argv[idx + 1])
    dashboard = api_get(f'dashboard/{dash_id}')
    print(f'Dashboard {dash_id}: {dashboard.get("name", "?")}\n')
    for dc in dashboard.get('dashcards', []):
        c = dc.get('card', {})
        if c.get('id'):
            card_ids.append(c['id'])
else:
    card_ids = [int(x) for x in sys.argv[2:]]

# Inspecter chaque carte
for card_id in card_ids:
    card = api_get(f'card/{card_id}')
    name = card.get('name', '?')
    db_id = card.get('database_id')
    dq = card.get('dataset_query', {})
    query_db = dq.get('database')
    query_type = dq.get('type', '?')

    print(f'=== Card {card_id}: {name} ===')
    print(f'  database_id={db_id}, query.database={query_db}, type={query_type}')

    if query_type == 'native':
        sql = dq.get('native', {}).get('query', '')[:100]
        print(f'  SQL: {sql}...')
    else:
        # MBQL - verifier field IDs et table IDs
        fids = find_field_ids(dq)
        tids = find_table_ids(dq)

        bad_fields = [f for f in fids if f not in valid_field_ids]
        bad_tables = [t for t in tids if t not in valid_table_ids]

        print(f'  Fields: {len(fids)} total, {len(bad_fields)} invalides')
        print(f'  Tables: {len(tids)} total, {len(bad_tables)} invalides')

        if bad_fields:
            print(f'  FIELD IDS INVALIDES: {bad_fields}')
        if bad_tables:
            print(f'  TABLE IDS INVALIDES: {bad_tables}')

        if not bad_fields and not bad_tables:
            # Tout semble OK - tester l'execution
            print(f'  IDs OK - test execution...')
            result = api_post('dataset', dq)
            if result.get('error'):
                print(f'  ERREUR EXECUTION: {str(result.get("error", ""))[:150]}')
            elif result.get('data', {}).get('rows') is not None:
                rows = len(result['data']['rows'])
                print(f'  Execution OK ({rows} lignes)')
            else:
                print(f'  Resultat inattendu')

    print()
