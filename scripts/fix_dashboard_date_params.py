"""Change le parametre date/range en date/month-year sur D4 et D15.

Comme D3 qui fonctionne parfaitement en embedding.

Usage :
    python scripts/fix_dashboard_date_params.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/fix_dashboard_date_params.py <token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'

# D4 = dashboard 5, D15 = dashboard 16, D16 = dashboard 17
DASHBOARDS_TO_FIX = [5, 16, 17]


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


for dash_id in DASHBOARDS_TO_FIX:
    dashboard = api_get(f'dashboard/{dash_id}')
    name = dashboard.get('name', '?')
    params = dashboard.get('parameters', [])

    print(f'=== Dashboard {dash_id}: {name} ===')

    new_params = []
    changed = False
    for p in params:
        if p.get('type') == 'date/range':
            print(f'  Parametre "{p.get("slug")}": date/range -> date/month-year')
            p['type'] = 'date/month-year'
            p['name'] = 'Mois'
            p['slug'] = 'mois'
            p['id'] = 'mois'
            changed = True
        new_params.append(p)

    if changed:
        # Mettre a jour les parameter_mappings pour utiliser le nouveau slug
        dashcards = dashboard.get('dashcards', [])
        new_dashcards = []
        for dc in dashcards:
            new_mappings = []
            for m in dc.get('parameter_mappings', []):
                if m.get('parameter_id') == 'date':
                    m['parameter_id'] = 'mois'
                new_mappings.append(m)
            new_dashcards.append({
                'id': dc['id'],
                'card_id': dc.get('card_id'),
                'row': dc.get('row', 0),
                'col': dc.get('col', 0),
                'size_x': dc.get('size_x', 4),
                'size_y': dc.get('size_y', 4),
                'parameter_mappings': new_mappings,
            })

        api_put(f'dashboard/{dash_id}', {
            'parameters': new_params,
            'dashcards': new_dashcards,
        })
        print(f'  CORRIGE')
    else:
        print(f'  Aucun changement')

print('\nTermine')
