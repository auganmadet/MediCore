"""Corrige les requetes SQL natives qui referencent MEDICORE au lieu de MEDICORE_PROD.

Scanne toutes les cartes des dashboards D1-D16 et remplace
'MEDICORE.MARTS.' par 'MEDICORE_PROD.MARTS.' dans les requetes natives.

Usage :
    python scripts/fix_cards_db_name.py <session_token>
    python scripts/fix_cards_db_name.py <session_token> --dry-run
"""

import json
import sys
import time
import urllib.request
import urllib.error

if len(sys.argv) < 2:
    print('Usage: python scripts/fix_cards_db_name.py <token> [--dry-run] [--start N]')
    sys.exit(1)

TOKEN = sys.argv[1]
DRY_RUN = '--dry-run' in sys.argv
BASE = 'http://localhost:3001/api'
ALL_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

start_id = 2
if '--start' in sys.argv:
    idx = sys.argv.index('--start')
    start_id = int(sys.argv[idx + 1])

DASHBOARD_IDS = [d for d in ALL_IDS if d >= start_id]
OLD_NAME = 'MEDICORE.'
NEW_NAME = 'MEDICORE_PROD.'


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


def replace_in_query(obj):
    """Remplace MEDICORE. par MEDICORE_PROD. dans les requetes natives."""
    changed = False
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == 'native' and isinstance(v, str) and OLD_NAME in v:
                new[k] = v.replace(OLD_NAME, NEW_NAME)
                changed = True
            else:
                result = replace_in_query(v)
                new[k] = result[0]
                changed = changed or result[1]
        return new, changed
    elif isinstance(obj, list):
        new = []
        for item in obj:
            result = replace_in_query(item)
            new.append(result[0])
            changed = changed or result[1]
        return new, changed
    elif isinstance(obj, str) and OLD_NAME in obj:
        return obj.replace(OLD_NAME, NEW_NAME), True
    return obj, False


print('=' * 60)
print(f'Fix MEDICORE -> MEDICORE_PROD (dry_run={DRY_RUN})')
print('=' * 60)

fixed = 0
skipped = 0
seen = set()

for i, dash_id in enumerate(DASHBOARD_IDS):
    if i > 0:
        time.sleep(3)

    dashboard = api_get(f'dashboard/{dash_id}')
    name = dashboard.get('name', '?')
    print(f'\n--- Dashboard {dash_id}: {name} ---')

    for dc in dashboard.get('dashcards', []):
        card = dc.get('card', {})
        card_id = card.get('id')
        if not card_id or card_id in seen:
            continue
        seen.add(card_id)

        full_card = api_get(f'card/{card_id}')
        dq = full_card.get('dataset_query', {})

        new_dq, changed = replace_in_query(dq)

        if not changed:
            continue

        card_name = full_card.get('name', '?')
        if DRY_RUN:
            print(f'  card {card_id}: TROUVEE ({card_name})')
            fixed += 1
        else:
            try:
                api_put(f'card/{card_id}', {'dataset_query': new_dq})
                print(f'  card {card_id}: CORRIGEE ({card_name})')
                fixed += 1
                time.sleep(2)
            except urllib.error.HTTPError as e:
                print(f'  card {card_id}: ERREUR ({e})')

print(f'\n=== RESUME ===')
print(f'  Corrigees: {fixed}')
