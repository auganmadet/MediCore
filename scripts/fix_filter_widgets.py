"""Verifie et corrige les filtres des dashboards D1-D16.

Force tous les filtres texte (Pharmacie, Fournisseur, Univers, etc.)
en mode "liste deroulante" au lieu de "champ de saisie".

Usage :
    python scripts/fix_filter_widgets.py <session_token>
    python scripts/fix_filter_widgets.py <session_token> --dry-run
"""

import json
import sys
import time
import urllib.request
import urllib.error

if len(sys.argv) < 2:
    print('Usage: python scripts/fix_filter_widgets.py <token> [--dry-run]')
    sys.exit(1)

TOKEN = sys.argv[1]
DRY_RUN = '--dry-run' in sys.argv
BASE = 'http://localhost:3000/api'
DASHBOARD_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

# Slugs des filtres texte qui doivent etre en liste deroulante
LIST_FILTER_SLUGS = {'pharmacie', 'fournisseur', 'univers', 'statut_dormant', 'operateur'}


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


print('=' * 60)
print(f'Fix filtres -> liste deroulante (dry_run={DRY_RUN})')
print('=' * 60)

fixed_total = 0

for i, dash_id in enumerate(DASHBOARD_IDS):
    if i > 0:
        time.sleep(3)

    dashboard = api_get(f'dashboard/{dash_id}')
    name = dashboard.get('name', '?')
    params = dashboard.get('parameters', [])

    changes = []
    new_params = []
    for p in params:
        slug = p.get('slug', '')
        if slug in LIST_FILTER_SLUGS:
            current_type = p.get('values_query_type', 'none')
            if current_type != 'list':
                p['values_query_type'] = 'list'
                changes.append(slug)
        new_params.append(p)

    if changes:
        print(f'\n--- Dashboard {dash_id}: {name} ---')
        for slug in changes:
            print(f'  {slug}: -> liste deroulante')
        if not DRY_RUN:
            api_put(f'dashboard/{dash_id}', {'parameters': new_params})
            print(f'  CORRIGE')
        else:
            print(f'  [DRY-RUN]')
        fixed_total += len(changes)

print(f'\n=== RESUME ===')
print(f'  Filtres corriges: {fixed_total}')
