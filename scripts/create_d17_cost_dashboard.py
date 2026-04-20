"""Creation du dashboard D17 - Couts Snowflake (plan Z6_7 etape 4).

Cree 4 cartes SQL natives dans la collection Qualite & Pilotage > Cards > Admin (id=33),
puis un dashboard D17 dans Qualite & Pilotage > Dashboards > Admin (id=34).

Admin = responsable MediCore (budget, supervision).
IT = equipe IT operationnelle.

Les cartes lisent MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS (alimentee par cost_monitoring.py).

Usage :
    python scripts/create_d17_cost_dashboard.py              # cree tout
    python scripts/create_d17_cost_dashboard.py --dry-run    # preview
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

MB_URL = os.getenv('METABASE_URL', 'http://metabase:3000')
MB_EMAIL = os.getenv('METABASE_ADMIN_EMAIL')
MB_PASSWORD = os.getenv('METABASE_ADMIN_PASSWORD')

SNOWFLAKE_DB_ID = 2  # MediCore database dans Metabase
CARDS_COLLECTION_ID = 33       # Qualite & Pilotage > Cards > Admin
DASHBOARDS_COLLECTION_ID = 34  # Qualite & Pilotage > Dashboards > Admin


CARD_DEFS = [
    {
        'name': 'D17 - Credits consommes ce mois',
        'description': 'Total des credits Snowflake consommes depuis le debut du mois en cours (tous warehouses).',
        'display': 'scalar',
        'sql': """
            SELECT
                COALESCE(SUM(CREDITS_USED), 0) AS credits_this_month
            FROM MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS
            WHERE USAGE_DATE >= DATE_TRUNC('month', CURRENT_DATE())
        """,
    },
    {
        'name': 'D17 - Credits restants sur quota mensuel',
        'description': 'Credits restants avant d\'atteindre le quota mensuel du Resource Monitor MEDICORE_MONITOR (600 credits).',
        'display': 'scalar',
        'sql': """
            SELECT
                COALESCE(AVG(CREDITS_REMAINING), 0) AS credits_remaining
            FROM MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS
            WHERE USAGE_DATE = (SELECT MAX(USAGE_DATE) FROM MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS)
        """,
    },
    {
        'name': 'D17 - Evolution quotidienne des credits (30 derniers jours)',
        'description': 'Credits consommes par jour sur les 30 derniers jours, tous warehouses confondus.',
        'display': 'line',
        'sql': """
            SELECT
                USAGE_DATE,
                SUM(CREDITS_USED) AS daily_credits
            FROM MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS
            WHERE USAGE_DATE >= DATEADD(day, -30, CURRENT_DATE())
            GROUP BY USAGE_DATE
            ORDER BY USAGE_DATE
        """,
    },
    {
        'name': 'D17 - Mois en cours vs mois precedent',
        'description': 'Comparaison du total des credits entre le mois en cours et le mois precedent.',
        'display': 'bar',
        'sql': """
            SELECT
                CASE
                    WHEN USAGE_DATE >= DATE_TRUNC('month', CURRENT_DATE())
                        THEN 'Ce mois'
                    ELSE 'Mois precedent'
                END AS periode,
                SUM(CREDITS_USED) AS credits
            FROM MEDICORE_PROD.AUDIT.SNOWFLAKE_CREDITS
            WHERE USAGE_DATE >= DATE_TRUNC('month', DATEADD(month, -1, CURRENT_DATE()))
            GROUP BY periode
            ORDER BY periode DESC
        """,
    },
]


def mb_login():
    req = urllib.request.Request(
        MB_URL + '/api/session',
        data=json.dumps({'username': MB_EMAIL, 'password': MB_PASSWORD}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())['id']


def mb_request(token, method, path, payload=None):
    headers = {'X-Metabase-Session': token, 'Content-Type': 'application/json'}
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(MB_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def find_existing(token, collection_id, name_prefix, kind):
    """Cherche des elements existants pour eviter les doublons."""
    path = '/api/card' if kind == 'card' else '/api/dashboard'
    items = mb_request(token, 'GET', path)
    return [i for i in items if i.get('collection_id') == collection_id and (i.get('name') or '').startswith(name_prefix)]


def create_card(token, card_def, dry_run=False):
    payload = {
        'name': card_def['name'],
        'description': card_def['description'],
        'display': card_def['display'],
        'collection_id': CARDS_COLLECTION_ID,
        'dataset_query': {
            'database': SNOWFLAKE_DB_ID,
            'type': 'native',
            'native': {'query': card_def['sql'].strip()},
        },
        'visualization_settings': {},
    }
    if dry_run:
        logger.info('[DRY] card: %s', card_def['name'])
        return {'id': None, 'name': card_def['name']}
    result = mb_request(token, 'POST', '/api/card', payload)
    logger.info('Card cree : id=%s name=%s', result['id'], result['name'])
    return result


def create_dashboard(token, name, description, dry_run=False):
    payload = {
        'name': name,
        'description': description,
        'collection_id': DASHBOARDS_COLLECTION_ID,
    }
    if dry_run:
        logger.info('[DRY] dashboard: %s', name)
        return {'id': None, 'name': name}
    result = mb_request(token, 'POST', '/api/dashboard', payload)
    logger.info('Dashboard cree : id=%s name=%s', result['id'], result['name'])
    return result


def add_cards_to_dashboard(token, dashboard_id, cards, dry_run=False):
    """Ajoute les cartes au dashboard via PUT /api/dashboard/{id}.

    Layout 2x2 : 2 scalaires en haut, line + bar en bas.
    """
    dashcards = []
    positions = [
        (0, 0, 6, 3),   # credits ce mois : top-left
        (6, 0, 6, 3),   # credits restants : top-right
        (0, 3, 12, 5),  # line : row 2 full width
        (0, 8, 12, 4),  # bar : row 3 full width
    ]
    for i, (card, pos) in enumerate(zip(cards, positions)):
        col, row, w, h = pos
        dashcards.append({
            'id': -(i + 1),  # negative IDs = new cards
            'card_id': card['id'],
            'col': col,
            'row': row,
            'size_x': w,
            'size_y': h,
            'visualization_settings': {},
            'parameter_mappings': [],
        })

    if dry_run:
        logger.info('[DRY] add %d cards to dashboard %s', len(dashcards), dashboard_id)
        return

    result = mb_request(token, 'PUT', f'/api/dashboard/{dashboard_id}', {'dashcards': dashcards})
    logger.info('Dashboard mis a jour avec %d cartes', len(dashcards))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans creation')
    args = parser.parse_args()

    if not MB_EMAIL or not MB_PASSWORD:
        logger.error('METABASE_ADMIN_EMAIL / METABASE_ADMIN_PASSWORD absents du .env')
        sys.exit(1)

    token = mb_login()
    logger.info('Metabase auth OK')

    # Verifier l'existence
    existing_cards = find_existing(token, CARDS_COLLECTION_ID, 'D17 - ', 'card')
    existing_dashboards = find_existing(token, DASHBOARDS_COLLECTION_ID, 'D17 ', 'dashboard')
    if existing_cards:
        logger.warning('Cartes D17 existantes (ids=%s). Abandon pour eviter doublons.',
                       [c['id'] for c in existing_cards])
        sys.exit(2)
    if existing_dashboards:
        logger.warning('Dashboard D17 existant (id=%s). Abandon pour eviter doublon.',
                       existing_dashboards[0]['id'])
        sys.exit(2)

    # Creer les cartes
    cards = [create_card(token, c, dry_run=args.dry_run) for c in CARD_DEFS]

    # Creer le dashboard
    dashboard = create_dashboard(
        token,
        'D17 - Couts Snowflake (Admin)',
        'Suivi de la consommation de credits Snowflake : mois courant, quota restant, evolution quotidienne, comparaison mois precedent. Alimente par cost_monitoring.py.',
        dry_run=args.dry_run,
    )

    # Ajouter cartes au dashboard
    if not args.dry_run and dashboard.get('id'):
        add_cards_to_dashboard(token, dashboard['id'], cards, dry_run=args.dry_run)
        logger.info('D17 pret : %s/dashboard/%s', MB_URL, dashboard['id'])


if __name__ == '__main__':
    main()
