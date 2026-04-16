"""Verifie les metadonnees de champs Metabase.

Usage :
    python scripts/check_fields.py <session_token> <field_id> [field_id ...]
"""

import json
import sys
import urllib.request

if len(sys.argv) < 3:
    print('Usage: python scripts/check_fields.py <token> <field_id> [field_id ...]')
    sys.exit(1)

TOKEN = sys.argv[1]
FIELD_IDS = [int(x) for x in sys.argv[2:]]

for fid in FIELD_IDS:
    req = urllib.request.Request(
        f'http://localhost:3000/api/field/{fid}',
        headers={'X-Metabase-Session': TOKEN},
    )
    f = json.loads(urllib.request.urlopen(req, timeout=30).read())
    print(f'Field {fid}:')
    print(f'  name={f.get("name")}')
    print(f'  table_id={f.get("table_id")}')
    print(f'  has_field_values={f.get("has_field_values")}')
    print(f'  semantic_type={f.get("semantic_type")}')
    print(f'  base_type={f.get("base_type")}')
    print()
