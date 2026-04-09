"""Test exhaustif des permissions Metabase OSS pour un utilisateur pharmacien.

Teste via l'API (pas l'UI) chaque point bloquant :
- P1 : SQL natif bloque sur MediCore ?
- P2 : Dashboard Admin modifiable ?
- P3 : Peut creer une carte dans sa collection ?
- P4 : Peut creer une carte dans une collection Admin ?
- P5 : Peut voir les donnees via query builder ?
- P6 : Acces a toutes les pharmacies via query builder ?

Usage :
    python scripts/check_permissions.py <email> <password>
"""

import json
import sys
import urllib.request
import urllib.error

if len(sys.argv) < 3:
    print('Usage: python scripts/check_permissions.py <email> <password>')
    sys.exit(1)

EMAIL = sys.argv[1]
PASSWORD = sys.argv[2]
BASE = 'http://localhost:3000/api'
MEDICORE_DB_ID = 2
ADMIN_DASHBOARD_ID = 2  # D1


def api_call(method, path, token, data=None):
    """Appel API avec gestion d'erreur."""
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method=method,
        headers={
            'X-Metabase-Session': token,
            'Content-Type': 'application/json; charset=utf-8',
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return {'status': resp.status, 'data': json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {'status': e.code, 'error': body}


# ============================================================
# LOGIN
# ============================================================

print('=' * 60)
print(f'TEST PERMISSIONS METABASE -- {EMAIL}')
print('=' * 60)

login_data = json.dumps({'username': EMAIL, 'password': PASSWORD}).encode()
req = urllib.request.Request(
    f'{BASE}/session', data=login_data, method='POST',
    headers={'Content-Type': 'application/json'},
)
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    token = resp['id']
    print(f'\nLogin: OK (token={token[:12]}...)')
except Exception as e:
    print(f'\nLogin: ECHEC ({e})')
    sys.exit(1)

# User info
user = api_call('GET', 'user/current', token)['data']
print(f'User: {user["common_name"]} (id={user["id"]})')
print(f'Superuser: {user.get("is_superuser", False)}')
groups = user.get('user_group_memberships', [])
print(f'Groupes: {[g.get("id") for g in groups]}')

# ============================================================
# P1 -- SQL NATIF SUR MEDICORE
# ============================================================

print(f'\n{"=" * 60}')
print('P1 -- SQL natif sur MediCore (doit etre BLOQUE)')
print('=' * 60)

result = api_call('POST', 'dataset', token, {
    'database': MEDICORE_DB_ID,
    'type': 'native',
    'native': {'query': 'SELECT COUNT(*) FROM MARTS.DIM_PHARMACIE'},
})

if result.get('error') or result.get('data', {}).get('error'):
    error_msg = result.get('error', '') or result.get('data', {}).get('error', '')
    print(f'  Resultat: BLOQUE OK')
    print(f'  Message: {error_msg[:100]}')
else:
    rows = result.get('data', {}).get('data', {}).get('rows', [])
    print(f'  Resultat: AUTORISE FAIL (retourne {rows})')
    print(f'  -> Le pharmacien peut executer du SQL natif !')

# ============================================================
# P2 -- MODIFICATION DASHBOARD ADMIN
# ============================================================

print(f'\n{"=" * 60}')
print(f'P2 -- Modification dashboard Admin D1 (id={ADMIN_DASHBOARD_ID}) (doit etre BLOQUE)')
print('=' * 60)

# Lire le dashboard d'abord
dash = api_call('GET', f'dashboard/{ADMIN_DASHBOARD_ID}', token)
if dash.get('error'):
    print(f'  Lecture dashboard: BLOQUE ({dash["status"]})')
    print(f'  -> Le pharmacien ne peut meme pas voir le dashboard')
else:
    print(f'  Lecture dashboard: OK (nom={dash["data"].get("name", "?")})')

    # Tenter de modifier le nom
    original_name = dash['data']['name']
    test_name = original_name + ' [TEST MODIF]'

    modify_result = api_call('PUT', f'dashboard/{ADMIN_DASHBOARD_ID}', token, {
        'name': test_name,
    })

    if modify_result.get('error') or modify_result.get('status', 0) >= 400:
        print(f'  Modification nom: BLOQUE OK (HTTP {modify_result.get("status", "?")})')
        print(f'  Message: {str(modify_result.get("error", ""))[:100]}')
    else:
        new_name = modify_result.get('data', {}).get('name', '')
        if new_name == test_name:
            print(f'  Modification nom: AUTORISE FAIL (renomme en "{test_name}")')
            print(f'  -> RESTAURATION...')
            api_call('PUT', f'dashboard/{ADMIN_DASHBOARD_ID}', token, {
                'name': original_name,
            })
            print(f'  -> Restaure en "{original_name}"')
        else:
            print(f'  Modification nom: IGNORE (nom inchange: "{new_name}")')

    # Tenter de supprimer une carte du dashboard
    dashcards = dash['data'].get('dashcards', [])
    if dashcards:
        print(f'  Dashboard a {len(dashcards)} cartes')
        # Tenter de mettre a jour les dashcards (supprimer la derniere)
        reduced = [{'id': dc['id'], 'card_id': dc.get('card_id'),
                     'row': dc.get('row', 0), 'col': dc.get('col', 0),
                     'size_x': dc.get('size_x', 4), 'size_y': dc.get('size_y', 4),
                     'parameter_mappings': dc.get('parameter_mappings', [])}
                    for dc in dashcards[:-1]]

        modify_cards = api_call('PUT', f'dashboard/{ADMIN_DASHBOARD_ID}', token, {
            'dashcards': reduced,
        })

        if modify_cards.get('error') or modify_cards.get('status', 0) >= 400:
            print(f'  Suppression carte: BLOQUE OK')
        else:
            new_count = len(modify_cards.get('data', {}).get('dashcards', []))
            if new_count < len(dashcards):
                print(f'  Suppression carte: AUTORISE FAIL ({len(dashcards)} -> {new_count})')
                print(f'  -> RESTAURATION...')
                restore = [{'id': dc['id'], 'card_id': dc.get('card_id'),
                           'row': dc.get('row', 0), 'col': dc.get('col', 0),
                           'size_x': dc.get('size_x', 4), 'size_y': dc.get('size_y', 4),
                           'parameter_mappings': dc.get('parameter_mappings', [])}
                          for dc in dashcards]
                api_call('PUT', f'dashboard/{ADMIN_DASHBOARD_ID}', token, {
                    'dashcards': restore,
                })
                print(f'  -> Restaure ({len(dashcards)} cartes)')
            else:
                print(f'  Suppression carte: IGNORE (meme nombre)')

# ============================================================
# P3 -- CREATION CARTE DANS SA COLLECTION
# ============================================================

print(f'\n{"=" * 60}')
print('P3 -- Creation carte dans sa collection Pharmacie du Soleil (doit etre AUTORISE)')
print('=' * 60)

# Trouver la collection Pharmacie du Soleil
collections = api_call('GET', 'collection', token)['data']
pharma_coll = None
for c in collections:
    if c.get('name') == 'Pharmacie du Soleil' and not c.get('archived'):
        pharma_coll = c
        break

if not pharma_coll:
    print('  Collection Pharmacie du Soleil: NON TROUVEE')
else:
    print(f'  Collection: id={pharma_coll["id"]}')
    create_card = api_call('POST', 'card', token, {
        'name': '_TEST_PERMISSION_CARD',
        'dataset_query': {
            'database': MEDICORE_DB_ID,
            'type': 'query',
            'query': {'source-table': 33},  # une table MARTS
        },
        'display': 'table',
        'visualization_settings': {},
        'collection_id': pharma_coll['id'],
    })

    if create_card.get('error') or create_card.get('status', 0) >= 400:
        print(f'  Creation carte: BLOQUE FAIL (devrait etre autorise)')
        print(f'  Message: {str(create_card.get("error", ""))[:100]}')
    else:
        card_id = create_card['data']['id']
        print(f'  Creation carte: AUTORISE OK (card_id={card_id})')
        # Nettoyer
        api_call('PUT', f'card/{card_id}', token, {'archived': True})
        print(f'  -> Nettoye (archive)')

# ============================================================
# P4 -- CREATION CARTE DANS COLLECTION ADMIN
# ============================================================

print(f'\n{"=" * 60}')
print('P4 -- Creation carte dans collection Admin (doit etre BLOQUE)')
print('=' * 60)

create_admin_card = api_call('POST', 'card', token, {
    'name': '_TEST_ADMIN_CARD',
    'dataset_query': {
        'database': MEDICORE_DB_ID,
        'type': 'query',
        'query': {'source-table': 33},
    },
    'display': 'table',
    'visualization_settings': {},
    'collection_id': 21,  # Admin collection
})

if create_admin_card.get('error') or create_admin_card.get('status', 0) >= 400:
    print(f'  Creation dans Admin: BLOQUE OK')
    print(f'  Message: {str(create_admin_card.get("error", ""))[:100]}')
else:
    card_id = create_admin_card['data']['id']
    print(f'  Creation dans Admin: AUTORISE FAIL (card_id={card_id})')
    api_call('PUT', f'card/{card_id}', token, {'archived': True})
    print(f'  -> Nettoye')

# ============================================================
# P5 -- QUERY BUILDER (ACCES DONNEES)
# ============================================================

print(f'\n{"=" * 60}')
print('P5 -- Query builder sur MediCore (doit etre AUTORISE)')
print('=' * 60)

qb_result = api_call('POST', 'dataset', token, {
    'database': MEDICORE_DB_ID,
    'type': 'query',
    'query': {
        'source-table': 33,
        'limit': 5,
    },
})

if qb_result.get('error') or qb_result.get('data', {}).get('error'):
    print(f'  Query builder: BLOQUE FAIL (devrait etre autorise)')
else:
    rows = qb_result.get('data', {}).get('data', {}).get('rows', [])
    print(f'  Query builder: AUTORISE OK ({len(rows)} lignes)')

# ============================================================
# P6 -- TOUTES LES PHARMACIES VISIBLES (PAS DE RLS)
# ============================================================

print(f'\n{"=" * 60}')
print('P6 -- Nombre de pharmacies visibles (sans RLS = toutes)')
print('=' * 60)

count_result = api_call('POST', 'dataset', token, {
    'database': MEDICORE_DB_ID,
    'type': 'query',
    'query': {
        'source-table': 33,
        'aggregation': [['count']],
    },
})

if count_result.get('error') or count_result.get('data', {}).get('error'):
    print(f'  Comptage: ERREUR')
else:
    rows = count_result.get('data', {}).get('data', {}).get('rows', [])
    count = rows[0][0] if rows else '?'
    print(f'  Pharmacies visibles: {count}')
    if isinstance(count, int) and count > 1:
        print(f'  -> TOUTES les pharmacies sont visibles (pas de RLS) WARN')
    elif count == 1:
        print(f'  -> 1 seule pharmacie visible (RLS actif) OK')

# ============================================================
# RESUME
# ============================================================

print(f'\n{"=" * 60}')
print('RESUME')
print('=' * 60)
print('''
  ┌─────┬──────────────────────────────────────────┬──────────┐
  │  #  │ Test                                     │ Attendu  │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P1  │ SQL natif bloque sur MediCore            │ BLOQUE   │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P2  │ Dashboard Admin non modifiable           │ BLOQUE   │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P3  │ Carte creable dans sa collection         │ AUTORISE │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P4  │ Carte non creable dans Admin             │ BLOQUE   │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P5  │ Query builder fonctionne                 │ AUTORISE │
  ├─────┼──────────────────────────────────────────┼──────────┤
  │ P6  │ Toutes pharmacies visibles (pas de RLS)  │ TOUTES   │
  └─────┴──────────────────────────────────────────┴──────────┘

  Voir les resultats ci-dessus pour les preuves concretes.
''')
