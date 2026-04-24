"""Recupere ou genere la cle secrete d'embedding Metabase.

Usage :
    python scripts/get_embedding_key.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/get_embedding_key.py <session_token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'

# Activer l'embedding statique (signed)
req = urllib.request.Request(
    f'{BASE}/setting/enable-embedding-static',
    data=json.dumps({'value': True}).encode(),
    method='PUT',
    headers={
        'X-Metabase-Session': TOKEN,
        'Content-Type': 'application/json',
    },
)
urllib.request.urlopen(req, timeout=30)
print('Signed embedding: active')

# Recuperer la cle secrete
req = urllib.request.Request(
    f'{BASE}/setting/embedding-secret-key',
    headers={'X-Metabase-Session': TOKEN},
)
resp = urllib.request.urlopen(req, timeout=30).read().decode()
print(f'Cle secrete: {resp}')
