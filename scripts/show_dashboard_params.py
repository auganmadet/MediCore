"""Affiche les parametres et parameter_mappings d'un dashboard.

Usage :
    python scripts/show_dashboard_params.py <session_token> <dashboard_id>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 3:
    print('Usage: python scripts/show_dashboard_params.py <token> <dash_id>')
    sys.exit(1)

TOKEN = sys.argv[1]
DASH_ID = sys.argv[2]

req = urllib.request.Request(
    f'http://localhost:3001/api/dashboard/{DASH_ID}',
    headers={'X-Metabase-Session': TOKEN},
)
dash = json.loads(urllib.request.urlopen(req, timeout=120).read())

print(f'Dashboard {DASH_ID}: {dash.get("name", "?")}')
print(f'\nParametres du dashboard:')
for p in dash.get('parameters', []):
    print(f'  - slug={p.get("slug")} name={p.get("name")} type={p.get("type")} id={p.get("id")}')

print(f'\nParameter mappings par carte:')
for dc in dash.get('dashcards', []):
    card = dc.get('card', {})
    card_id = card.get('id')
    card_name = card.get('name', '?')[:30]
    mappings = dc.get('parameter_mappings', [])
    if mappings:
        print(f'  Card {card_id} ({card_name}):')
        for m in mappings:
            print(f'    param={m.get("parameter_id")} -> target={json.dumps(m.get("target"))}')
    else:
        print(f'  Card {card_id} ({card_name}): AUCUN MAPPING')
