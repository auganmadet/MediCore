"""Cree les cartes 369 et 405 en MBQL (query builder) pour remplacer les SQL natives.

Usage :
    python scripts/create_mbql_cards.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/create_mbql_cards.py <token>')
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


# D'abord, trouver les field IDs pour les tables concernees
print('Chargement metadata...')
meta = api_get('database/2/metadata?include_hidden=false')

marge_table_id = None
marge_fields = {}
ventes_table_id = None
ventes_fields = {}

for t in meta.get('tables', []):
    if t['name'] == 'MART_KPI_MARGE':
        marge_table_id = t['id']
        for f in t.get('fields', []):
            marge_fields[f['name']] = f['id']
    elif t['name'] == 'FACT_VENTES':
        ventes_table_id = t['id']
        for f in t.get('fields', []):
            ventes_fields[f['name']] = f['id']

print(f'  MART_KPI_MARGE: table_id={marge_table_id}')
print(f'    TAUX_MARGE={marge_fields.get("TAUX_MARGE")}')
print(f'    PHARMACIE_SK={marge_fields.get("PHARMACIE_SK")}')
print(f'    DATE_JOUR={marge_fields.get("DATE_JOUR")}')
print(f'  FACT_VENTES: table_id={ventes_table_id}')
print(f'    ORD_CLIENT_AGE_MONTHS={ventes_fields.get("ORD_CLIENT_AGE_MONTHS")}')
print(f'    CA_TTC={ventes_fields.get("CA_TTC")}')
print(f'    PHARMACIE_SK={ventes_fields.get("PHARMACIE_SK")}')
print(f'    DATE_VENTE={ventes_fields.get("DATE_VENTE")}')

# ============================================================
# Carte 1 : Distribution taux de marge (MBQL)
# ============================================================
print('\n=== Creation: Distribution taux de marge (MBQL) ===')

taux_marge_id = marge_fields['TAUX_MARGE']

card1 = api_post('card', {
    'name': 'Distribution taux de marge',
    'display': 'bar',
    'database_id': 2,
    'dataset_query': {
        'database': 2,
        'type': 'query',
        'query': {
            'source-table': marge_table_id,
            'aggregation': [['count']],
            'breakout': [
                ['expression', 'tranche_marge'],
            ],
            'expressions': {
                'tranche_marge': [
                    'case',
                    [
                        [['<', ['field', taux_marge_id, None], 0], '< 0%'],
                        [['<', ['field', taux_marge_id, None], 0.1], '0-10%'],
                        [['<', ['field', taux_marge_id, None], 0.2], '10-20%'],
                        [['<', ['field', taux_marge_id, None], 0.3], '20-30%'],
                        [['<', ['field', taux_marge_id, None], 0.4], '30-40%'],
                        [['<', ['field', taux_marge_id, None], 0.5], '40-50%'],
                    ],
                    {'default': '50%+'},
                ],
            },
        },
    },
    'visualization_settings': {},
    'collection_id': 21,
})
card1_id = card1['id']
print(f'  Creee: card_id={card1_id}')

# ============================================================
# Carte 2 : CA par tranche d'age (MBQL)
# ============================================================
print('\n=== Creation: CA par tranche d age (MBQL) ===')

age_id = ventes_fields['ORD_CLIENT_AGE_MONTHS']
ca_ttc_id = ventes_fields['CA_TTC']

card2 = api_post('card', {
    'name': "CA par tranche d'age",
    'display': 'bar',
    'database_id': 2,
    'dataset_query': {
        'database': 2,
        'type': 'query',
        'query': {
            'source-table': ventes_table_id,
            'aggregation': [['sum', ['field', ca_ttc_id, None]]],
            'breakout': [
                ['expression', 'tranche_age'],
            ],
            'expressions': {
                'tranche_age': [
                    'case',
                    [
                        [['is-null', ['field', age_id, None]], 'Inconnu'],
                        [['<', ['field', age_id, None], 216], '0-17 ans'],
                        [['<', ['field', age_id, None], 468], '18-38 ans'],
                        [['<', ['field', age_id, None], 720], '39-59 ans'],
                        [['<', ['field', age_id, None], 960], '60-79 ans'],
                    ],
                    {'default': '80+ ans'},
                ],
            },
            'order-by': [['desc', ['aggregation', 0]]],
        },
    },
    'visualization_settings': {},
    'collection_id': 21,
})
card2_id = card2['id']
print(f'  Creee: card_id={card2_id}')

# ============================================================
# Remplacer les anciennes cartes dans les dashboards
# ============================================================
print(f'\n=== Remplacement dans les dashboards ===')
print(f'  Nouvelle carte Distribution taux de marge: {card1_id} (remplace 369)')
print(f'  Nouvelle carte CA par tranche d age: {card2_id} (remplace 405)')
print(f'\n  Pour remplacer dans les dashboards:')
print(f'  1. Ouvrir D4 -> mode edition -> supprimer carte 369 -> ajouter carte {card1_id}')
print(f'  2. Ouvrir D15 -> mode edition -> supprimer carte 405 -> ajouter carte {card2_id}')
print(f'  3. Connecter les filtres Pharmacie et Mois aux nouvelles cartes')
print(f'\n  Ou lancer: python scripts/replace_cards_in_dashboards.py <token> {card1_id} {card2_id}')
