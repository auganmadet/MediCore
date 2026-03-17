"""Corrige les parameter_mappings null dans tous les dashboards Metabase."""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = sys.argv[1]


def api_get(path):
    """Récupère une ressource Metabase via GET."""
    req = urllib.request.Request(
        'http://localhost:3000/api/' + path,
        headers={'X-Metabase-Session': TOKEN}
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_put(path, data):
    """Met à jour une ressource Metabase via PUT."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:3000/api/' + path, data=body, method='PUT',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8'
        }
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


# Type mapping par nom de paramètre
BASE_TYPES = {
    'pharmacie': 'type/Text',
    'mois': 'type/Date',
    'date': 'type/Date',
    'fournisseur': 'type/Text',
    'operateur': 'type/Text',
    'univers': 'type/Text',
    'statut_dormant': 'type/Text',
    'produit': 'type/Text',
}

total_fixed = 0

for did in range(2, 18):
    d = api_get(f'dashboard/{did}')
    dashcards = d.get('dashcards', [])
    fixed_count = 0

    for dc in dashcards:
        for pm in dc.get('parameter_mappings', []):
            target = pm.get('target', [])
            if (len(target) == 2
                    and isinstance(target[1], list)
                    and len(target[1]) == 3
                    and target[1][2] is None):
                param_id = pm.get('parameter_id', '')
                base_type = BASE_TYPES.get(param_id, 'type/Text')
                target[1][2] = {'base-type': base_type}
                fixed_count += 1

    if fixed_count > 0:
        api_put(f'dashboard/{did}', {'dashcards': dashcards})
        total_fixed += fixed_count
        print(f'Dashboard {did} ({d["name"]}): {fixed_count} mappings corrigés')
    else:
        print(f'Dashboard {did}: OK')

print(f'\nTotal : {total_fixed} mappings corrigés')
