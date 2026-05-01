"""
Ajoute un utilisateur Metabase associé à un service.

Usage :
    python scripts/add_metabase_user.py <session_token> <email> <prenom> <nom> <service>

Exemple :
    python scripts/add_metabase_user.py "abc-123" "jean.dupont@mediprix.fr" "Jean" "Dupont" "IT"

Gouvernance des collections :
    MediCore BI/
    ├── Achats & Stock/
    │   ├── Cards/
    │   │   ├── Admin/          (lecture seule pour les services)
    │   │   └── <Service>/      (curate pour le service concerné)
    │   └── Dashboards/
    │       ├── Admin/          (lecture seule pour les services)
    │       └── <Service>/      (curate pour le service concerné)
    ├── Direction Générale/
    │   └── ...
    └── ...

Droits :
    - Collections parentes + Admin : view (lecture, filtrer, exporter)
    - Sous-collections de son service : curate (créer ses dashboards/cartes)
    - Données Snowflake : lecture seule, query-builder (pas de SQL natif)
"""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

if len(sys.argv) < 6:
    print('Usage: python add_metabase_user.py <session_token> <email> <prenom> <nom> <service>')
    print('Exemple: python add_metabase_user.py "abc-123" "jean@mediprix.fr" "Jean" "Dupont" "IT"')
    sys.exit(1)

TOKEN = sys.argv[1]
EMAIL = sys.argv[2]
PRENOM = sys.argv[3]
NOM = sys.argv[4]
SERVICE = sys.argv[5]

BASE = 'http://localhost:3001/api'

# Collections parentes (contiennent Cards/ et Dashboards/)
PARENT_COLLS = {
    6: 'Direction Générale',
    7: 'Ventes & Performance',
    8: 'Achats & Stock',
    9: 'Qualité & Pilotage',
    10: 'Détail opérationnel',
}


def api_get(path):
    """GET sur l'API Metabase."""
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN}
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_post(path, data):
    """POST sur l'API Metabase."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='POST',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8'
        }
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_put(path, data):
    """PUT sur l'API Metabase."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='PUT',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8'
        }
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def find_or_create_collection(name, parent_id):
    """Trouve ou crée une sous-collection."""
    colls = api_get('collection')
    existing = next(
        (c for c in colls if c.get('name') == name and c.get('parent_id') == parent_id),
        None
    )
    if existing:
        return existing['id'], False
    new_coll = api_post('collection', {'name': name, 'parent_id': parent_id})
    return new_coll['id'], True


# ============================================================
# 1. Créer le groupe du service (s'il n'existe pas)
# ============================================================
print(f'=== Configuration pour {PRENOM} {NOM} — Service {SERVICE} ===\n')

groups = api_get('permissions/group')
service_group = next((g for g in groups if g['name'] == SERVICE), None)

if service_group:
    group_id = service_group['id']
    print(f'1. Groupe "{SERVICE}" existant : id={group_id}')
else:
    result = api_post('permissions/group', {'name': SERVICE})
    group_id = result['id']
    print(f'1. Groupe "{SERVICE}" créé : id={group_id}')

# ============================================================
# 2. Structure des collections : Admin/ + Service/ dans chaque Cards/ et Dashboards/
# ============================================================
print(f'\n2. Structure des collections :')

colls = api_get('collection')

# Trouver les sous-collections Cards/ et Dashboards/ de chaque parent
cards_colls = {}
dash_colls = {}
for c in colls:
    if c.get('name') == 'Cards' and c.get('parent_id') in PARENT_COLLS:
        cards_colls[c['parent_id']] = c['id']
    elif c.get('name') == 'Dashboards' and c.get('parent_id') in PARENT_COLLS:
        dash_colls[c['parent_id']] = c['id']

# Pour chaque Cards/ et Dashboards/, créer Admin/ et Service/
admin_coll_ids = []
service_coll_ids = []

for pid, pname in PARENT_COLLS.items():
    cards_id = cards_colls.get(pid)
    dash_id = dash_colls.get(pid)

    if not cards_id or not dash_id:
        print(f'  SKIP {pname}: Cards/ ou Dashboards/ manquant')
        continue

    # Cards/Admin/
    cid, created = find_or_create_collection('Admin', cards_id)
    admin_coll_ids.append(cid)
    if created:
        print(f'  {pname}/Cards/Admin/ créé (id={cid})')

    # Cards/<Service>/
    cid, created = find_or_create_collection(SERVICE, cards_id)
    service_coll_ids.append(cid)
    if created:
        print(f'  {pname}/Cards/{SERVICE}/ créé (id={cid})')

    # Dashboards/Admin/
    cid, created = find_or_create_collection('Admin', dash_id)
    admin_coll_ids.append(cid)
    if created:
        print(f'  {pname}/Dashboards/Admin/ créé (id={cid})')

    # Dashboards/<Service>/
    cid, created = find_or_create_collection(SERVICE, dash_id)
    service_coll_ids.append(cid)
    if created:
        print(f'  {pname}/Dashboards/{SERVICE}/ créé (id={cid})')

# ============================================================
# 3. Déplacer les cartes et dashboards existants dans Admin/
# ============================================================
print(f'\n3. Déplacement des éléments existants dans Admin/ :')

moved_cards = 0
moved_dash = 0

for pid, pname in PARENT_COLLS.items():
    cards_id = cards_colls.get(pid)
    dash_id = dash_colls.get(pid)
    if not cards_id or not dash_id:
        continue

    # Trouver Admin/ dans Cards/ et Dashboards/
    colls_fresh = api_get('collection')
    admin_cards = next(
        (c['id'] for c in colls_fresh if c.get('name') == 'Admin' and c.get('parent_id') == cards_id),
        None
    )
    admin_dash = next(
        (c['id'] for c in colls_fresh if c.get('name') == 'Admin' and c.get('parent_id') == dash_id),
        None
    )

    if not admin_cards or not admin_dash:
        continue

    # Déplacer les cartes qui sont directement dans Cards/ (pas dans un sous-dossier)
    items = api_get(f'collection/{cards_id}/items')
    for item in items.get('data', []):
        if item['model'] == 'card' and item.get('collection_id') == cards_id:
            api_put(f'card/{item["id"]}', {'collection_id': admin_cards})
            moved_cards += 1

    # Déplacer les dashboards qui sont directement dans Dashboards/
    items = api_get(f'collection/{dash_id}/items')
    for item in items.get('data', []):
        if item['model'] == 'dashboard' and item.get('collection_id') == dash_id:
            api_put(f'dashboard/{item["id"]}', {'collection_id': admin_dash})
            moved_dash += 1

print(f'  {moved_cards} cartes déplacées dans Admin/')
print(f'  {moved_dash} dashboards déplacés dans Admin/')

# ============================================================
# 4. Créer le compte utilisateur
# ============================================================
print(f'\n4. Création du compte :')

user = api_post('user', {
    'email': EMAIL,
    'first_name': PRENOM,
    'last_name': NOM,
    'password': 'Medicore2026!',
})
user_id = user['id']
print(f'  Utilisateur id={user_id}, email={EMAIL}')
print(f'  Mot de passe temporaire : Medicore2026!')

# Affecter au groupe du service
api_post(f'permissions/group/{group_id}/membership', {'user_id': user_id})
print(f'  Ajouté au groupe "{SERVICE}"')

# ============================================================
# 5. Permissions données (DB 2 = Snowflake)
# ============================================================
print(f'\n5. Permissions données :')

perms = api_get('permissions/graph')
perms['groups'][str(group_id)] = {
    '2': {
        'view-data': 'unrestricted',
        'create-queries': 'query-builder',
        'download': {'schemas': 'full'},
    }
}
api_put('permissions/graph', perms)
print(f'  Snowflake : view-data=unrestricted, create-queries=query-builder, download=full')

# ============================================================
# 6. Permissions collections
# ============================================================
print(f'\n6. Permissions collections :')

coll_perms = api_get('collection/graph')
group_key = str(group_id)

if group_key not in coll_perms['groups']:
    coll_perms['groups'][group_key] = {}

gp = coll_perms['groups'][group_key]

# MediCore BI : lecture
gp['5'] = 'read'

# Collections parentes : lecture
for pid in PARENT_COLLS:
    gp[str(pid)] = 'read'

# Cards/ et Dashboards/ : lecture
for cid in list(cards_colls.values()) + list(dash_colls.values()):
    gp[str(cid)] = 'read'

# Admin/ : lecture
for aid in admin_coll_ids:
    gp[str(aid)] = 'read'

# Service/ : curate (créer)
for sid in service_coll_ids:
    gp[str(sid)] = 'write'

api_put('collection/graph', coll_perms)
print(f'  MediCore BI + parents + Cards/ + Dashboards/ + Admin/ : view')
print(f'  {SERVICE}/ ({len(service_coll_ids)} sous-collections) : curate')

# ============================================================
# RÉSUMÉ
# ============================================================
print(f'\n{"="*60}')
print(f'RÉSUMÉ — {PRENOM} {NOM} ({EMAIL})')
print(f'{"="*60}')
print(f'Service : {SERVICE} (groupe id={group_id})')
print(f'')
print(f'Peut :')
print(f'  ✓ Voir tous les dashboards/cartes Admin (lecture seule)')
print(f'  ✓ Filtrer et exporter les données')
print(f'  ✓ Créer des questions (MBQL, pas SQL natif)')
print(f'  ✓ Créer des cartes dans Cards/{SERVICE}/')
print(f'  ✓ Créer des dashboards dans Dashboards/{SERVICE}/')
print(f'')
print(f'Ne peut pas :')
print(f'  ✗ Modifier ou supprimer les dashboards/cartes Admin')
print(f'  ✗ Modifier les dashboards/cartes des autres services')
print(f'  ✗ Écrire du SQL natif')
print(f'  ✗ Accéder à l\'administration Metabase')
