"""Remplace les cartes SQL natives 369 et 405 par les nouvelles MBQL dans D4 et D15.

Usage :
    python scripts/replace_cards_in_dashboards.py <token> <new_card1_id> <new_card2_id>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 4:
    print('Usage: python scripts/replace_cards_in_dashboards.py <token> <card1_id> <card2_id>')
    sys.exit(1)

TOKEN = sys.argv[1]
NEW_CARD_369 = int(sys.argv[2])
NEW_CARD_405 = int(sys.argv[3])
BASE = 'http://localhost:3000/api'

REPLACEMENTS = {
    5: {369: NEW_CARD_369},   # D4: Distribution taux de marge
    16: {405: NEW_CARD_405},  # D15: CA par tranche d'age
}


def api_get(path):
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN},
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


# Charger metadata pour les field IDs des nouvelles cartes
meta = api_get('database/2/metadata?include_hidden=false')
field_ids = {}
for t in meta.get('tables', []):
    for f in t.get('fields', []):
        field_ids[(t['name'], f['name'])] = f['id']

# Mapping field IDs pour les filtres
PHARMACIE_SK_MARGE = field_ids[('MART_KPI_MARGE', 'PHARMACIE_SK')]
DATE_JOUR_MARGE = field_ids[('MART_KPI_MARGE', 'DATE_JOUR')]
PHARMACIE_SK_VENTES = field_ids[('FACT_VENTES', 'PHARMACIE_SK')]
DATE_VENTE = field_ids[('FACT_VENTES', 'DATE_VENTE')]


for dash_id, card_map in REPLACEMENTS.items():
    dashboard = api_get(f'dashboard/{dash_id}')
    name = dashboard.get('name', '?')
    print(f'=== Dashboard {dash_id}: {name} ===')

    new_dashcards = []
    for dc in dashboard.get('dashcards', []):
        old_card_id = dc.get('card_id')

        if old_card_id in card_map:
            new_card_id = card_map[old_card_id]
            print(f'  Remplacement carte {old_card_id} -> {new_card_id}')

            # Determiner les field IDs pour les filtres
            if new_card_id == NEW_CARD_369:
                pharma_field = PHARMACIE_SK_MARGE
                date_field = DATE_JOUR_MARGE
            else:
                pharma_field = PHARMACIE_SK_VENTES
                date_field = DATE_VENTE

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
                        'target': ['dimension', ['field', pharma_field, {'base-type': 'type/Text'}]],
                    },
                    {
                        'parameter_id': 'mois',
                        'card_id': new_card_id,
                        'target': ['dimension', ['field', date_field, {'base-type': 'type/Date'}]],
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

    api_put(f'dashboard/{dash_id}', {'dashcards': new_dashcards})
    print(f'  OK')

print('\nTermine')
