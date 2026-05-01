"""Affiche le dataset_query complet d'une carte Metabase.

Usage :
    python scripts/show_card_query.py <session_token> <card_id>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 3:
    print('Usage: python scripts/show_card_query.py <token> <card_id>')
    sys.exit(1)

TOKEN = sys.argv[1]
CARD_ID = sys.argv[2]

req = urllib.request.Request(
    f'http://localhost:3001/api/card/{CARD_ID}',
    headers={'X-Metabase-Session': TOKEN},
)
card = json.loads(urllib.request.urlopen(req, timeout=60).read())

print(f'Card {CARD_ID}: {card.get("name", "?")}')
print(f'database_id: {card.get("database_id")}')
print(f'dataset_query:')
print(json.dumps(card.get('dataset_query', {}), indent=2))
