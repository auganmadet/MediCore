"""Recree une carte SQL native en MBQL (query builder) et la remplace dans son dashboard.

Analyse la carte SQL native, identifie la table et les colonnes, construit
l'equivalent MBQL, cree la nouvelle carte et remplace dans le dashboard
avec les bons parameter_mappings.

Usage :
    python scripts/create_mbql_card.py --card 369
    python scripts/create_mbql_card.py --card 369 --card 405 --card 407
    python scripts/create_mbql_card.py --card 369 --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

BASE_URL = os.getenv('METABASE_URL', os.getenv('METABASE_SITE_URL', 'http://localhost:3001'))
BASE = f'{BASE_URL}/api'
DB_ID = int(os.getenv('MB_SOURCE_DATABASE_ID', '2'))
ADMIN_COLLECTION_ID = 21


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
    req = urllib.request.Request(
        f'{BASE}/{path}', headers={'X-Metabase-Session': token},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def api_post(token, path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='POST',
        headers={'X-Metabase-Session': token, 'Content-Type': 'application/json'},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def api_put(token, path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='PUT',
        headers={'X-Metabase-Session': token, 'Content-Type': 'application/json'},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def load_metadata(token):
    """Charge les metadata de toutes les tables MARTS."""
    meta = api_get(token, f'database/{DB_ID}/metadata?include_hidden=false')
    tables = {}
    for t in meta.get('tables', []):
        fields = {f['name']: f['id'] for f in t.get('fields', [])}
        tables[t['name']] = {'id': t['id'], 'fields': fields}
    return tables


def find_dashboard_for_card(token, card_id):
    """Trouve le dashboard qui contient une carte donnee."""
    dashboard_ids = list(range(2, 18))
    for dash_id in dashboard_ids:
        dash = api_get(token, f'dashboard/{dash_id}')
        for dc in dash.get('dashcards', []):
            if dc.get('card_id') == card_id:
                return dash_id, dc
    return None, None


def extract_table_from_sql(sql):
    """Extrait le nom de table FROM d'un SQL natif."""
    match = re.search(r'FROM\s+\w+\.MARTS\.(\w+)', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


# ============================================================
# Definitions MBQL des cartes connues
# ============================================================

KNOWN_CARDS = {
    369: {
        'name': 'Distribution taux de marge',
        'display': 'bar',
        'table': 'MART_KPI_MARGE',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['count']],
            'breakout': [['expression', 'tranche_marge']],
            'expressions': {
                'tranche_marge': [
                    'case',
                    [
                        [['<', ['field', fields['TAUX_MARGE'], None], 0], '< 0%'],
                        [['<', ['field', fields['TAUX_MARGE'], None], 0.1], '0-10%'],
                        [['<', ['field', fields['TAUX_MARGE'], None], 0.2], '10-20%'],
                        [['<', ['field', fields['TAUX_MARGE'], None], 0.3], '20-30%'],
                        [['<', ['field', fields['TAUX_MARGE'], None], 0.4], '30-40%'],
                        [['<', ['field', fields['TAUX_MARGE'], None], 0.5], '40-50%'],
                    ],
                    {'default': '50%+'},
                ],
            },
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'DATE_JOUR'},
    },
    405: {
        'name': "CA par tranche d'age",
        'display': 'bar',
        'table': 'FACT_VENTES',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['sum', ['field', fields['CA_TTC'], None]]],
            'breakout': [['expression', 'tranche_age']],
            'expressions': {
                'tranche_age': [
                    'case',
                    [
                        [['is-null', ['field', fields['ORD_CLIENT_AGE_MONTHS'], None]], 'Inconnu'],
                        [['<', ['field', fields['ORD_CLIENT_AGE_MONTHS'], None], 216], '0-17 ans'],
                        [['<', ['field', fields['ORD_CLIENT_AGE_MONTHS'], None], 468], '18-38 ans'],
                        [['<', ['field', fields['ORD_CLIENT_AGE_MONTHS'], None], 720], '39-59 ans'],
                        [['<', ['field', fields['ORD_CLIENT_AGE_MONTHS'], None], 960], '60-79 ans'],
                    ],
                    {'default': '80+ ans'},
                ],
            },
            'order-by': [['desc', ['aggregation', 0]]],
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'DATE_VENTE'},
    },
    407: {
        'name': 'Taux de marge par univers',
        'display': 'bar',
        'table': 'MART_KPI_MARGE_PAR_UNIVERS',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['avg', ['field', fields['TAUX_MARGE_PCT'], None]]],
            'breakout': [['field', fields['UNIVERS'], None]],
            'order-by': [['desc', ['aggregation', 0]]],
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'univers': 'UNIVERS'},
    },
    49: {
        'name': 'Repartition modes de paiement',
        'display': 'pie',
        'table': 'MART_KPI_TRESORERIE',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [
                ['sum', ['field', fields['PCT_CB'], None]],
                ['sum', ['field', fields['PCT_ESPECES'], None]],
                ['sum', ['field', fields['PCT_CHEQUES'], None]],
                ['sum', ['field', fields['PCT_TIERS_PAYANT'], None]],
                ['sum', ['field', fields['PCT_VIREMENT'], None]],
            ],
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'MOIS'},
    },
    366: {
        'name': 'TVA par taux',
        'display': 'bar',
        'table': 'FACT_TRESORERIE',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [
                ['sum', ['field', fields['TVA_TAUX1'], None]],
                ['sum', ['field', fields['TVA_TAUX2'], None]],
                ['sum', ['field', fields['TVA_TAUX3'], None]],
                ['sum', ['field', fields['TVA_TAUX4'], None]],
                ['sum', ['field', fields['TVA_TAUX5'], None]],
            ],
            'breakout': [
                ['field', fields['DATE_JOUR'], {'temporal-unit': 'month'}],
            ],
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'DATE_JOUR'},
    },
    373: {
        'name': 'Top 10 produits en rupture',
        'display': 'bar',
        'table': 'MART_KPI_RUPTURES_PAR_PRODUIT',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['sum', ['field', fields['NB_BOITES_MANQUANTES'], None]]],
            'breakout': [['field', fields['PRD_NOM'], None]],
            'order-by': [['desc', ['aggregation', 0]]],
            'limit': 10,
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'MOIS'},
    },
    374: {
        'name': 'Jours de rupture par produit',
        'display': 'bar',
        'table': 'MART_KPI_RUPTURES_PAR_PRODUIT',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['sum', ['field', fields['NB_JOURS_RUPTURE'], None]]],
            'breakout': [
                ['field', fields['PRD_NOM'], None],
                ['field', fields['MOIS'], None],
            ],
            'order-by': [['desc', ['aggregation', 0]]],
            'limit': 20,
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'MOIS'},
    },
    384: {
        'name': 'Ecoulement par fournisseur',
        'display': 'bar',
        'table': 'MART_KPI_ECOULEMENT_PAR_FOURNISSEUR',
        'build': lambda fields: {
            'source-table': None,
            'aggregation': [['avg', ['field', fields['TAUX_ECOULEMENT'], None]]],
            'breakout': [['field', fields['FOU_NOM'], None]],
            'filter': ['not-null', ['field', fields['TAUX_ECOULEMENT'], None]],
            'order-by': [['desc', ['aggregation', 0]]],
            'limit': 15,
        },
        'filter_columns': {'pharmacie': 'PHARMACIE_SK', 'mois': 'MOIS'},
    },
}


def create_mbql_card(token, card_id, tables, dry_run):
    """Cree une carte MBQL et remplace l'ancienne dans le dashboard."""
    if card_id not in KNOWN_CARDS:
        print(f'  Card {card_id}: INCONNUE (pas dans KNOWN_CARDS)')
        print(f'  Ajouter la definition dans KNOWN_CARDS du script')
        return None

    definition = KNOWN_CARDS[card_id]
    table_name = definition['table']

    if table_name not in tables:
        print(f'  Card {card_id}: table {table_name} non trouvee dans metadata')
        return None

    table_info = tables[table_name]
    table_id = table_info['id']
    fields = table_info['fields']

    print(f'  Table: {table_name} (id={table_id})')

    query = definition['build'](fields)
    query['source-table'] = table_id

    if dry_run:
        print(f'  [DRY-RUN] Creerait carte MBQL "{definition["name"]}"')
        return None

    new_card = api_post(token, 'card', {
        'name': definition['name'],
        'display': definition['display'],
        'database_id': DB_ID,
        'dataset_query': {
            'database': DB_ID,
            'type': 'query',
            'query': query,
        },
        'visualization_settings': {},
        'collection_id': ADMIN_COLLECTION_ID,
    })
    new_card_id = new_card['id']
    print(f'  Carte MBQL creee: card_id={new_card_id}')

    # Remplacer dans le dashboard
    dash_id, dashcard = find_dashboard_for_card(token, card_id)
    if not dash_id:
        print(f'  Dashboard non trouve pour card {card_id}')
        return new_card_id

    print(f'  Remplacement dans dashboard {dash_id}...')
    dashboard = api_get(token, f'dashboard/{dash_id}')

    # Construire les parameter_mappings pour la nouvelle carte
    filter_cols = definition['filter_columns']
    new_mappings = []
    for param_slug, col_name in filter_cols.items():
        if col_name in fields:
            base_type = 'type/Date' if 'DATE' in col_name else 'type/Text'
            new_mappings.append({
                'parameter_id': param_slug,
                'card_id': new_card_id,
                'target': ['dimension', ['field', fields[col_name], {'base-type': base_type}]],
            })

    new_dashcards = []
    for dc in dashboard.get('dashcards', []):
        if dc.get('card_id') == card_id:
            new_dashcards.append({
                'id': dc['id'],
                'card_id': new_card_id,
                'row': dc.get('row', 0),
                'col': dc.get('col', 0),
                'size_x': dc.get('size_x', 4),
                'size_y': dc.get('size_y', 4),
                'parameter_mappings': new_mappings,
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

    api_put(token, f'dashboard/{dash_id}', {'dashcards': new_dashcards})
    print(f'  Dashboard {dash_id}: carte {card_id} -> {new_card_id} OK')
    return new_card_id


def main():
    parser = argparse.ArgumentParser(description='Recree des cartes SQL natives en MBQL')
    parser.add_argument('--card', type=int, action='append', required=True,
                        help='ID de la carte a recreer (peut etre repete)')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans modification')
    args = parser.parse_args()

    print('=' * 60)
    print(f'Recreation cartes SQL natives -> MBQL (dry_run={args.dry_run})')
    print('=' * 60)

    token = get_token()
    print('Authentification Metabase: OK')

    tables = load_metadata(token)
    print(f'Metadata: {len(tables)} tables chargees\n')

    for card_id in args.card:
        print(f'=== Card {card_id} ===')
        create_mbql_card(token, card_id, tables, args.dry_run)
        time.sleep(2)
        print()

    print('Termine')


if __name__ == '__main__':
    main()
