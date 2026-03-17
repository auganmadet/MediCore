"""
Provisionne les utilisateurs Metabase depuis config/metabase_users.csv.

Idempotent : ne recrée pas les comptes/groupes/collections existants.
Désactive les comptes marqués actif=non.

Usage :
    python scripts/provision_metabase_users.py <session_token>

Format CSV (config/metabase_users.csv) :
    email,prenom,nom,service,actif
    jean.dupont@mediprix.fr,Jean,Dupont,IT,oui
    marie.martin@mediprix.fr,Marie,Martin,Comptabilité,oui
    pierre.durand@mediprix.fr,Pierre,Durand,IT,non

Gouvernance :
    - Admin/ : cartes et dashboards créés par l'administrateur (lecture seule)
    - <Service>/ : espace de travail du service (curate)
    - Collections parentes : lecture seule pour tous les services
"""
import csv
import os
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

if len(sys.argv) < 2:
    print('Usage: python provision_metabase_users.py <session_token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3000/api'
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'metabase_users.csv')
# Mot de passe temporaire (utilisé uniquement si SMTP non configuré)
# Si SMTP est configuré, Metabase envoie un email d'invitation et
# l'utilisateur définit son propre mot de passe via le lien.
DEFAULT_PASSWORD = 'Medicore2026!'

PARENT_COLLS = {
    6: 'Direction Générale',
    7: 'Ventes & Performance',
    8: 'Achats & Stock',
    9: 'Qualité & Pilotage',
    10: 'Détail opérationnel',
}
MEDICORE_COLL = 5


# ============================================================
# API helpers
# ============================================================

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


# ============================================================
# Cache helpers (évite les appels API répétés)
# ============================================================

_collections_cache = None


def get_collections():
    """Récupère toutes les collections (avec cache)."""
    global _collections_cache
    if _collections_cache is None:
        _collections_cache = api_get('collection')
    return _collections_cache


def invalidate_collections_cache():
    """Force le rechargement du cache."""
    global _collections_cache
    _collections_cache = None


def find_collection(name, parent_id):
    """Trouve une collection par nom et parent."""
    colls = get_collections()
    return next(
        (c for c in colls if c.get('name') == name and c.get('parent_id') == parent_id),
        None
    )


def find_or_create_collection(name, parent_id):
    """Trouve ou crée une sous-collection. Retourne (id, created)."""
    existing = find_collection(name, parent_id)
    if existing:
        return existing['id'], False
    new_coll = api_post('collection', {'name': name, 'parent_id': parent_id})
    invalidate_collections_cache()
    return new_coll['id'], True


# ============================================================
# Lecture du CSV
# ============================================================

def read_users_csv():
    """Lit le fichier CSV et retourne la liste des utilisateurs."""
    users = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Ignorer les lignes commentées
            if row.get('email', '').startswith('#'):
                continue
            if not row.get('email', '').strip():
                continue
            users.append({
                'email': row['email'].strip(),
                'prenom': row['prenom'].strip(),
                'nom': row['nom'].strip(),
                'service': row['service'].strip(),
                'actif': row.get('actif', 'oui').strip().lower() in ('oui', 'true', '1', 'yes'),
            })
    return users


# ============================================================
# Provisionnement
# ============================================================

def get_existing_users():
    """Récupère tous les utilisateurs Metabase existants."""
    users = api_get('user')
    return {u['email']: u for u in users.get('data', users) if isinstance(u, dict)}


def get_existing_groups():
    """Récupère tous les groupes existants."""
    groups = api_get('permissions/group')
    return {g['name']: g for g in groups}


def ensure_group(service, existing_groups):
    """Crée le groupe du service s'il n'existe pas."""
    if service in existing_groups:
        return existing_groups[service]['id']
    result = api_post('permissions/group', {'name': service})
    existing_groups[service] = result
    return result['id']


def ensure_structure(service):
    """Crée la structure Admin/ + Service/ dans chaque Cards/ et Dashboards/."""
    admin_ids = []
    service_ids = []

    colls = get_collections()
    cards_map = {c['parent_id']: c['id'] for c in colls
                 if c.get('name') == 'Cards' and c.get('parent_id') in PARENT_COLLS}
    dash_map = {c['parent_id']: c['id'] for c in colls
                if c.get('name') == 'Dashboards' and c.get('parent_id') in PARENT_COLLS}

    for pid in PARENT_COLLS:
        cards_id = cards_map.get(pid)
        dash_id = dash_map.get(pid)
        if not cards_id or not dash_id:
            continue

        # Admin/
        aid, created = find_or_create_collection('Admin', cards_id)
        admin_ids.append(aid)
        if created:
            print(f'    Créé : {PARENT_COLLS[pid]}/Cards/Admin/')

        aid, created = find_or_create_collection('Admin', dash_id)
        admin_ids.append(aid)
        if created:
            print(f'    Créé : {PARENT_COLLS[pid]}/Dashboards/Admin/')

        # Service/
        sid, created = find_or_create_collection(service, cards_id)
        service_ids.append(sid)
        if created:
            print(f'    Créé : {PARENT_COLLS[pid]}/Cards/{service}/')

        sid, created = find_or_create_collection(service, dash_id)
        service_ids.append(sid)
        if created:
            print(f'    Créé : {PARENT_COLLS[pid]}/Dashboards/{service}/')

    return admin_ids, service_ids, list(cards_map.values()), list(dash_map.values())


def move_orphans_to_admin():
    """Déplace les cartes/dashboards sans sous-collection dans Admin/."""
    colls = get_collections()
    cards_map = {c['parent_id']: c['id'] for c in colls
                 if c.get('name') == 'Cards' and c.get('parent_id') in PARENT_COLLS}
    dash_map = {c['parent_id']: c['id'] for c in colls
                if c.get('name') == 'Dashboards' and c.get('parent_id') in PARENT_COLLS}

    moved = 0
    for pid in PARENT_COLLS:
        cards_id = cards_map.get(pid)
        dash_id = dash_map.get(pid)
        if not cards_id or not dash_id:
            continue

        admin_cards = find_collection('Admin', cards_id)
        admin_dash = find_collection('Admin', dash_id)
        if not admin_cards or not admin_dash:
            continue

        # Cartes orphelines dans Cards/ (pas dans un sous-dossier)
        items = api_get(f'collection/{cards_id}/items')
        for item in items.get('data', []):
            if item['model'] == 'card':
                api_put(f'card/{item["id"]}', {'collection_id': admin_cards['id']})
                moved += 1

        # Dashboards orphelins dans Dashboards/
        items = api_get(f'collection/{dash_id}/items')
        for item in items.get('data', []):
            if item['model'] == 'dashboard':
                api_put(f'dashboard/{item["id"]}', {'collection_id': admin_dash['id']})
                moved += 1

    return moved


def set_data_permissions(group_id):
    """Configure les permissions données Snowflake pour un groupe."""
    perms = api_get('permissions/graph')
    perms['groups'][str(group_id)] = {
        '2': {
            'view-data': 'unrestricted',
            'create-queries': 'query-builder',
            'download': {'schemas': 'full'},
        }
    }
    api_put('permissions/graph', perms)


def set_collection_permissions(group_id, admin_ids, service_ids, cards_ids, dash_ids):
    """Configure les permissions collections pour un groupe."""
    coll_perms = api_get('collection/graph')
    gk = str(group_id)

    if gk not in coll_perms['groups']:
        coll_perms['groups'][gk] = {}

    gp = coll_perms['groups'][gk]

    # MediCore BI + parents : lecture
    gp[str(MEDICORE_COLL)] = 'read'
    for pid in PARENT_COLLS:
        gp[str(pid)] = 'read'

    # Cards/ et Dashboards/ : lecture
    for cid in cards_ids + dash_ids:
        gp[str(cid)] = 'read'

    # Admin/ : lecture
    for aid in admin_ids:
        gp[str(aid)] = 'read'

    # Service/ : curate
    for sid in service_ids:
        gp[str(sid)] = 'write'

    api_put('collection/graph', coll_perms)


# ============================================================
# Main
# ============================================================

def main():
    """Point d'entrée principal."""
    print('=' * 60)
    print('Provisionnement utilisateurs Metabase')
    print('=' * 60)

    # Lire le CSV
    users = read_users_csv()
    if not users:
        print('\nAucun utilisateur dans le CSV (lignes commentées ou fichier vide).')
        print(f'Éditez {CSV_PATH} et relancez.')
        sys.exit(0)

    print(f'\n{len(users)} utilisateur(s) dans le CSV :')
    for u in users:
        status = 'actif' if u['actif'] else 'INACTIF'
        print(f'  {u["prenom"]} {u["nom"]} ({u["email"]}) — {u["service"]} [{status}]')

    # Charger les données existantes
    existing_users = get_existing_users()
    existing_groups = get_existing_groups()
    services = list(set(u['service'] for u in users))

    # Créer la structure pour chaque service
    print(f'\n--- Structure des collections ---')
    all_admin_ids = []
    service_coll_map = {}

    for service in services:
        admin_ids, service_ids, cards_ids, dash_ids = ensure_structure(service)
        all_admin_ids = admin_ids
        service_coll_map[service] = {
            'admin_ids': admin_ids,
            'service_ids': service_ids,
            'cards_ids': cards_ids,
            'dash_ids': dash_ids,
        }

    # Déplacer les orphelins dans Admin/
    print(f'\n--- Déplacement des éléments orphelins ---')
    moved = move_orphans_to_admin()
    print(f'  {moved} éléments déplacés dans Admin/')

    # Provisionner chaque utilisateur
    print(f'\n--- Provisionnement des comptes ---')
    created_count = 0
    updated_count = 0
    deactivated_count = 0

    for u in users:
        email = u['email']
        service = u['service']
        group_id = ensure_group(service, existing_groups)
        sc = service_coll_map[service]

        if email in existing_users:
            existing = existing_users[email]
            uid = existing['id']

            if u['actif'] and not existing.get('is_active', True):
                # Réactiver
                api_put(f'user/{uid}', {'is_active': True})
                print(f'  RÉACTIVÉ : {u["prenom"]} {u["nom"]} ({email})')
                updated_count += 1
            elif not u['actif'] and existing.get('is_active', True):
                # Désactiver
                api_put(f'user/{uid}', {'is_active': False})
                print(f'  DÉSACTIVÉ : {u["prenom"]} {u["nom"]} ({email})')
                deactivated_count += 1
            else:
                print(f'  EXISTE : {u["prenom"]} {u["nom"]} ({email})')
        else:
            if not u['actif']:
                print(f'  IGNORÉ (inactif) : {u["prenom"]} {u["nom"]} ({email})')
                continue

            # Créer le compte
            # Si SMTP est configuré, Metabase envoie automatiquement
            # un email d'invitation avec lien pour définir le mot de passe.
            # Sinon, le mot de passe temporaire est utilisé.
            new_user = api_post('user', {
                'email': email,
                'first_name': u['prenom'],
                'last_name': u['nom'],
                'password': DEFAULT_PASSWORD,
            })
            uid = new_user['id']

            # Affecter au groupe
            api_post(f'permissions/group/{group_id}/membership', {'user_id': uid})

            # Vérifier si SMTP est configuré
            try:
                smtp_settings = api_get('email')
                smtp_configured = bool(smtp_settings.get('smtp-host'))
            except Exception:
                smtp_configured = False

            print(f'  CRÉÉ : {u["prenom"]} {u["nom"]} ({email}) — {service}')
            if smtp_configured:
                print(f'         Email d\'invitation envoyé automatiquement par Metabase')
            else:
                print(f'         SMTP non configuré — communiquer manuellement :')
                print(f'         URL : http://192.168.1.30:3000')
                print(f'         Mot de passe temporaire : {DEFAULT_PASSWORD}')
            created_count += 1

        # Permissions données (idempotent)
        set_data_permissions(group_id)

        # Permissions collections (idempotent)
        set_collection_permissions(
            group_id,
            sc['admin_ids'],
            sc['service_ids'],
            sc['cards_ids'],
            sc['dash_ids']
        )

    # Résumé
    print(f'\n{"="*60}')
    print(f'RÉSUMÉ')
    print(f'{"="*60}')
    print(f'  Créés : {created_count}')
    print(f'  Mis à jour : {updated_count}')
    print(f'  Désactivés : {deactivated_count}')
    print(f'  Déjà existants : {len(users) - created_count - updated_count - deactivated_count}')
    print(f'  Services : {", ".join(services)}')
    print(f'  Éléments déplacés dans Admin/ : {moved}')

    print(f'\nDroits par service :')
    print(f'  ✓ Voir dashboards/cartes Admin (lecture seule)')
    print(f'  ✓ Filtrer et exporter les données')
    print(f'  ✓ Créer des questions (MBQL, pas SQL natif)')
    print(f'  ✓ Créer cartes/dashboards dans son espace service')
    print(f'  ✗ Modifier/supprimer les éléments Admin ou autres services')
    print(f'  ✗ SQL natif / Administration Metabase')


if __name__ == '__main__':
    main()
