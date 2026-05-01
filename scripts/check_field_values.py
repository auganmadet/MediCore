"""Verifie les valeurs cachees d'un champ Metabase.

Usage :
    python scripts/check_field_values.py <session_token> <field_id> [field_id ...]
"""

import json
import sys
import urllib.request
import urllib.error

if len(sys.argv) < 3:
    print('Usage: python scripts/check_field_values.py <token> <field_id> [field_id ...]')
    sys.exit(1)

TOKEN = sys.argv[1]
FIELD_IDS = [int(x) for x in sys.argv[2:]]

for fid in FIELD_IDS:
    try:
        req = urllib.request.Request(
            f'http://localhost:3001/api/field/{fid}/values',
            headers={'X-Metabase-Session': TOKEN},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        values = resp.get('values', [])
        print(f'Field {fid}: {len(values)} valeurs')
        for v in values[:5]:
            print(f'  {v}')
        if len(values) > 5:
            print(f'  ... ({len(values)} total)')
    except urllib.error.HTTPError as e:
        print(f'Field {fid}: ERREUR {e.code}')
    print()
