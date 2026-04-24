"""Restaure database_id=2 sur toutes les cartes des dashboards D1-D16.

Usage :
    python scripts/fix_cards_db.py <session_token>
    python scripts/fix_cards_db.py <session_token> --start 3   (reprendre à D2)
"""

import json
import sys
import time
import urllib.request
import urllib.error

if len(sys.argv) < 2:
    print('Usage: python scripts/fix_cards_db.py <session_token> [--start N]')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'
TARGET_DB = 2  # ID de la connexion MediCore (Admin)
ALL_DASHBOARD_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

start_id = 2
if '--start' in sys.argv:
    idx = sys.argv.index('--start')
    start_id = int(sys.argv[idx + 1])

DASHBOARD_IDS = [d for d in ALL_DASHBOARD_IDS if d >= start_id]


def api_get(path, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f'{BASE}/{path}',
                headers={'X-Metabase-Session': TOKEN},
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                print(f'    Retry {attempt+1}/{retries} ({e})')
                time.sleep(5)
            else:
                raise


def api_put(path, data, retries=3):
    for attempt in range(retries):
        try:
            body = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                f'{BASE}/{path}', data=body, method='PUT',
                headers={
                    'X-Metabase-Session': TOKEN,
                    'Content-Type': 'application/json; charset=utf-8',
                },
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                print(f'    Retry {attempt+1}/{retries} ({e})')
                time.sleep(5)
            else:
                raise


fixed = 0
skipped = 0
errors = 0

for i, dash_id in enumerate(DASHBOARD_IDS):
    if i > 0:
        print('  Pause 10s entre dashboards...')
        time.sleep(10)
    print(f'\n--- Dashboard {dash_id} ---')
    dashboard = api_get(f'dashboard/{dash_id}')
    print(f'  Nom: {dashboard.get("name", "?")}')

    for j, dc in enumerate(dashboard.get('dashcards', [])):
        card = dc.get('card', {})
        card_id = card.get('id')
        if not card_id:
            continue

        if j > 0:
            time.sleep(2)

        full_card = api_get(f'card/{card_id}')
        current_db = full_card.get('database_id')
        query_db = full_card.get('dataset_query', {}).get('database')

        if current_db == TARGET_DB and query_db == TARGET_DB:
            print(f'  card {card_id}: OK (db={current_db})')
            skipped += 1
            continue

        # Fix dataset_query.database
        dq = full_card['dataset_query']
        dq['database'] = TARGET_DB

        try:
            api_put(f'card/{card_id}', {
                'database_id': TARGET_DB,
                'dataset_query': dq,
            })
            print(f'  card {card_id}: FIXED (db={current_db} -> {TARGET_DB}) {full_card.get("name", "")}')
            fixed += 1
            time.sleep(2)
        except Exception as e:
            print(f'  card {card_id}: ERROR {e}')
            errors += 1

print(f'\n=== RÉSUMÉ ===')
print(f'  Corrigées: {fixed}')
print(f'  Déjà OK:   {skipped}')
print(f'  Erreurs:    {errors}')
