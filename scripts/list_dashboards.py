"""Liste les dashboards D1-D16 avec leur collection.

Usage :
    python scripts/list_dashboards.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/list_dashboards.py <token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3000/api'
DASHBOARD_IDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]


def api_get(path):
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


# Charger les collections avec hierarchie
colls = {}
for c in api_get('collection'):
    colls[c['id']] = {'name': c.get('name', '?'), 'parent_id': c.get('parent_id')}


def get_full_path(coll_id):
    parts = []
    current = coll_id
    while current and current in colls:
        parts.append(colls[current]['name'])
        current = colls[current]['parent_id']
    return ' / '.join(reversed(parts))


print(f'{"ID":>4}  {"Dashboard":<40}  {"Collection (chemin complet)"}')
print('-' * 100)

for dash_id in DASHBOARD_IDS:
    dash = api_get(f'dashboard/{dash_id}')
    name = dash.get('name', '?')
    coll_id = dash.get('collection_id')
    path = get_full_path(coll_id)
    print(f'{dash_id:>4}  {name:<40}  {path}')
