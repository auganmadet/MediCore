"""Liste les utilisateurs Metabase.

Usage :
    python scripts/list_users.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/list_users.py <session_token>')
    sys.exit(1)

TOKEN = sys.argv[1]
req = urllib.request.Request(
    'http://localhost:3000/api/user',
    headers={'X-Metabase-Session': TOKEN},
)
data = json.loads(urllib.request.urlopen(req, timeout=60).read())
for u in data['data']:
    status = 'actif' if u.get('is_active') else 'inactif'
    print(f'{u["id"]:>3}  {status:<8}  {u["email"]:<40}  {u["common_name"]}')
