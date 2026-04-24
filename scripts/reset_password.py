"""Reset le mot de passe d'un utilisateur Metabase.

Usage :
    python scripts/reset_password.py <session_token> <user_id> <new_password>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 4:
    print('Usage: python scripts/reset_password.py <session_token> <user_id> <new_password>')
    sys.exit(1)

TOKEN = sys.argv[1]
USER_ID = sys.argv[2]
PASSWORD = sys.argv[3]

body = json.dumps({'password': PASSWORD}).encode('utf-8')
req = urllib.request.Request(
    f'http://localhost:3001/api/user/{USER_ID}/password',
    data=body, method='PUT',
    headers={
        'X-Metabase-Session': TOKEN,
        'Content-Type': 'application/json; charset=utf-8',
    },
)
urllib.request.urlopen(req, timeout=60)
print(f'Mot de passe de user {USER_ID} réinitialisé.')
