"""Recree la carte 407 (Taux de marge par univers) en MBQL.

Usage :
    python scripts/create_mbql_card_407.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/create_mbql_card_407.py <token>')
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
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='POST',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8',
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def api_put(path, data):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='PUT',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8',
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


# Trouver les field IDs pour MART_KPI_MARGE_PAR_UNIVERS
print('Chargement metadata...')
meta = api_get('database/2/metadata?include_hidden=false')

table_id = None
fields = {}
for t in meta.get('tables', []):
    if t['name'] == 'MART_KPI_MARGE_PAR_UNIVERS':
        table_id = t['id']
        for f in t.get('fields', []):
            fields[f['name']] = f['id']

print(f'  MART_KPI_MARGE_PAR_UNIVERS: table_id={table_id}')
print(f'    UNIVERS={fields.get("UNIVERS")}')
print(f'    TAUX_MARGE_PCT={fields.get("TAUX_MARGE_PCT")}')
print(f'    PHARMACIE_SK={fields.get("PHARMACIE_SK")}')

univers_id = fields['UNIVERS']
taux_id = fields['TAUX_MARGE_PCT']
pharma_id = fields['PHARMACIE_SK']

# Creer la carte MBQL
print('\n=== Creation: Taux de marge par univers (MBQL) ===')

card = api_post('card', {
    'name': 'Taux de marge par univers',
    'display': 'bar',
    'database_id': 2,
    'dataset_query': {
        'database': 2,
        'type': 'query',
        'query': {
            'source-table': table_id,
            'aggregation': [['avg', ['field', taux_id, None]]],
            'breakout': [['field', univers_id, None]],
            'order-by': [['desc', ['aggregation', 0]]],
        },
    },
    'visualization_settings': {},
    'collection_id': 21,
})

new_card_id = card['id']
print(f'  Creee: card_id={new_card_id}')

# Remplacer dans D4 (dashboard 5)
print('\n=== Remplacement dans D4 ===')
dashboard = api_get('dashboard/5')

new_dashcards = []
for dc in dashboard.get('dashcards', []):
    old_card_id = dc.get('card_id')

    if old_card_id == 407:
        print(f'  Remplacement carte 407 -> {new_card_id}')
        new_dashcards.append({
            'id': dc['id'],
            'card_id': new_card_id,
            'row': dc.get('row', 0),
            'col': dc.get('col', 0),
            'size_x': dc.get('size_x', 4),
            'size_y': dc.get('size_y', 4),
            'parameter_mappings': [
                {
                    'parameter_id': 'pharmacie',
                    'card_id': new_card_id,
                    'target': ['dimension', ['field', pharma_id, {'base-type': 'type/Text'}]],
                },
                {
                    'parameter_id': 'univers',
                    'card_id': new_card_id,
                    'target': ['dimension', ['field', univers_id, {'base-type': 'type/Text'}]],
                },
            ],
        })
    else:
        new_dashcards.append({
            'id': dc['id'],
            'card_id': dc.get('card_id'),
            'row': dc.get('row', 0),
            'col': dc.get('col', 0),
            'size_x': dc.get('size_x', 4),
            'size_y': dc.get('size_y', 4),
            'parameter_mappings': dc.get('parameter_mappings', []),
        })

api_put('dashboard/5', {'dashcards': new_dashcards})
print('  OK')

print(f'\nTermine. Nouvelle carte: {new_card_id} (remplace 407)')
