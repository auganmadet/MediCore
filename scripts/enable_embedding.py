"""Active l'embedding signe sur les 16 dashboards D1-D16.

Configure automatiquement :
- Pharmacie : locked (verrouille par le JWT)
- Tous les autres filtres : enabled (editables par le pharmacien)

Usage :
    python scripts/enable_embedding.py <session_token>
"""

import json
import sys
import time
import urllib.request
import urllib.error

if len(sys.argv) < 2:
    print('Usage: python scripts/enable_embedding.py <session_token> [--start N]')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3000/api'
ALL_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

start_id = 2
if '--start' in sys.argv:
    idx = sys.argv.index('--start')
    start_id = int(sys.argv[idx + 1])

DASHBOARD_IDS = [d for d in ALL_IDS if d >= start_id]
LOCKED_PARAMS = ['pharmacie']


def api_get(path):
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_put(path, data):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='PUT',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8',
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


print('=' * 60)
print('Activation embedding sur D1-D16')
print('=' * 60)

for i, dash_id in enumerate(DASHBOARD_IDS):
    if i > 0:
        time.sleep(3)

    dashboard = api_get(f'dashboard/{dash_id}')
    name = dashboard.get('name', '?')
    params = dashboard.get('parameters', [])

    # Construire embedding_params : pharmacie=locked, reste=enabled
    embedding_params = {}
    for p in params:
        slug = p.get('slug', '')
        if slug.lower() in LOCKED_PARAMS:
            embedding_params[slug] = 'locked'
        else:
            embedding_params[slug] = 'enabled'

    # Activer l'embedding sur le dashboard
    try:
        api_put(f'dashboard/{dash_id}', {
            'enable_embedding': True,
            'embedding_params': embedding_params,
        })
        param_summary = ', '.join(f'{k}={v}' for k, v in embedding_params.items())
        print(f'  D{dash_id-1:>2} ({name}): OK [{param_summary}]')
    except urllib.error.HTTPError as e:
        print(f'  D{dash_id-1:>2} ({name}): ERREUR ({e})')

print('\n' + '=' * 60)
print('Termine')
print('=' * 60)
