"""Audit automatique complet de Metabase : requêtes, accents, descriptions, filtres."""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = sys.argv[1]


def api_get(path):
    """GET sur l'API Metabase."""
    req = urllib.request.Request(
        'http://localhost:3001/api/' + path,
        headers={'X-Metabase-Session': TOKEN}
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def api_post(path, data):
    """POST sur l'API Metabase."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:3001/api/' + path, data=body, method='POST',
        headers={'X-Metabase-Session': TOKEN, 'Content-Type': 'application/json; charset=utf-8'}
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


ACCENT_MAP = [
    ('Synthese', 'Synthèse'), ('Tresorerie', 'Trésorerie'),
    ('Ecoulement', 'Écoulement'), ('ecoulement', 'écoulement'),
    ('Evolution', 'Évolution'), ('evolution', 'évolution'),
    ('Generique', 'Générique'), ('generique', 'générique'),
    ('Repartition', 'Répartition'), ('repartition', 'répartition'),
    ('detaillee', 'détaillée'), ('Detaillee', 'Détaillée'),
    ('ponderee', 'pondérée'), ('Ponderee', 'Pondérée'),
    ('estimee', 'estimée'), ('Estimee', 'Estimée'),
    ('operateur', 'opérateur'), ('Operateur', 'Opérateur'),
    ('Fraicheur', 'Fraîcheur'), ('fraicheur', 'fraîcheur'),
    ('Qualite', 'Qualité'), ('qualite', 'qualité'),
    ('recentes', 'récentes'), ('Recentes', 'Récentes'),
    ('Detail ', 'Détail '), ('fidelite', 'fidélité'),
    ('Fidelite', 'Fidélité'), ('Retrocessions', 'Rétrocessions'),
    ('negatives', 'négatives'), ('Negatives', 'Négatives'),
    ('immobilise', 'immobilisé'), ('Immobilise', 'Immobilisé'),
    ('bloquee', 'bloquée'), ('Bloquee', 'Bloquée'),
    ('cumule', 'cumulé'), ('lissee', 'lissée'),
    ('impactes', 'impactés'), ('Impactes', 'Impactés'),
    ('sur-stockes', 'sur-stockés'),
    ('Commande ', 'Commandé '), ('commande ', 'commandé '),
    ('estime ', 'estimé '),
]

issues = []


def check_accents(text, context_type, context_name, context_id):
    """Vérifie les accents manquants dans un texte."""
    for bad, good in ACCENT_MAP:
        if bad in text and good not in text:
            issues.append((f'ACCENT_{context_type}', context_name, context_id, text[:60], f'{bad} -> {good}'))


# 1. TEST CARTES
print('=== TEST 1: Requêtes des 98 cartes ===')
query_errors = 0
query_empty = 0
card_count = 0
for did in range(2, 18):
    d = api_get(f'dashboard/{did}')
    dname = d['name']
    for dc in d.get('dashcards', []):
        card = dc.get('card', {})
        cid = card.get('id')
        if not cid:
            continue
        cname = card.get('name', '?')
        cdesc = card.get('description') or ''
        card_count += 1

        # Test query execution
        try:
            result = api_post(f'card/{cid}/query', {})
            err = result.get('error')
            rows = result.get('data', {}).get('rows', [])
            if err:
                query_errors += 1
                issues.append(('QUERY_ERROR', dname, cid, cname, err[:120]))
                print(f'  [ERREUR] {cname} (id={cid}): {err[:80]}')
            elif len(rows) == 0:
                query_empty += 1
                issues.append(('NO_DATA', dname, cid, cname, '0 rows'))
                print(f'  [VIDE] {cname} (id={cid})')
            else:
                sys.stdout.write('.')
                sys.stdout.flush()
        except Exception as e:
            query_errors += 1
            issues.append(('QUERY_EXCEPTION', dname, cid, cname, str(e)[:120]))
            print(f'  [EXCEPTION] {cname} (id={cid}): {str(e)[:80]}')

        # Check accents in card name
        check_accents(cname, 'CARD_NAME', cname, cid)

        # Check accents in description
        if cdesc:
            check_accents(cdesc, 'CARD_DESC', cname, cid)
        else:
            issues.append(('NO_DESC_CARD', dname, cid, cname, 'description vide'))

print(f'\n{card_count} cartes testées: {query_errors} erreurs, {query_empty} vides\n')

# 2. TEST DASHBOARDS
print('=== TEST 2: Dashboards noms/descriptions/accents ===')
for did in range(2, 18):
    d = api_get(f'dashboard/{did}')
    dname = d['name']
    ddesc = d.get('description') or ''
    check_accents(dname, 'DASH_NAME', dname, did)
    if ddesc:
        check_accents(ddesc, 'DASH_DESC', dname, did)
    else:
        issues.append(('NO_DESC_DASH', dname, did, dname, 'description vide'))
        print(f'  [VIDE] Dashboard {did} ({dname}): pas de description')

# 3. TEST COLLECTIONS
print('\n=== TEST 3: Collections accents ===')
colls = api_get('collection')
for c in colls:
    if c.get('personal_owner_id') is None and c['id'] != 'root':
        cname = c.get('name', '')
        cdesc = c.get('description') or ''
        check_accents(cname, 'COLL_NAME', cname, c['id'])
        if cdesc:
            check_accents(cdesc, 'COLL_DESC', cname, c['id'])

# 4. TEST FILTRES CASCADES
print('\n=== TEST 4: Filtres cascadés ===')
expected_cascading = {
    5: {'univers': ['pharmacie']},
    6: {'operateur': ['pharmacie']},
    11: {'fournisseur': ['pharmacie']},
    12: {'statut_dormant': ['pharmacie'], 'univers': ['pharmacie'], 'fournisseur': ['pharmacie']},
    14: {'fournisseur': ['pharmacie'], 'univers': ['pharmacie']},
}
for did, expected in expected_cascading.items():
    d = api_get(f'dashboard/{did}')
    params = {p['id']: p for p in d.get('parameters', [])}
    for pid, expected_fp in expected.items():
        actual_fp = params.get(pid, {}).get('filteringParameters', [])
        if actual_fp != expected_fp:
            issues.append(('FILTER_CASCADE', d['name'], did, pid, f'attendu {expected_fp}, got {actual_fp}'))
            print(f'  [CASCADE] Dashboard {did} filtre {pid}: attendu {expected_fp}, got {actual_fp}')

# 5. TEST MAPPINGS FILTRES - chaque carte mappée à chaque filtre du dashboard
print('\n=== TEST 5: Mappings filtres cartes/dashboards ===')
unmapped_count = 0
for did in range(2, 18):
    d = api_get(f'dashboard/{did}')
    params = d.get('parameters', [])
    if not params:
        continue
    for dc in d.get('dashcards', []):
        card = dc.get('card', {})
        if not card.get('id'):
            continue
        mapped_params = {pm['parameter_id'] for pm in dc.get('parameter_mappings', [])}
        for p in params:
            if p['id'] not in mapped_params:
                unmapped_count += 1
                issues.append(('UNMAPPED_FILTER', d['name'], card['id'], card.get('name', '?'), f'filtre {p["id"]}'))

# RAPPORT FINAL
print('\n' + '=' * 70)
print(f'RAPPORT AUDIT METABASE — {len(issues)} problèmes détectés')
print('=' * 70)

categories = {}
for i in issues:
    cat = i[0]
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(i)

for cat in ['QUERY_ERROR', 'QUERY_EXCEPTION', 'NO_DATA', 'ACCENT_CARD_NAME',
            'ACCENT_CARD_DESC', 'ACCENT_DASH_NAME', 'ACCENT_DASH_DESC',
            'ACCENT_COLL_NAME', 'ACCENT_COLL_DESC', 'NO_DESC_CARD',
            'NO_DESC_DASH', 'FILTER_CASCADE', 'UNMAPPED_FILTER']:
    items = categories.get(cat, [])
    if items:
        print(f'\n--- {cat} ({len(items)}) ---')
        for i in items:
            print(f'  {i[1]} > {i[3]} : {i[4]}')

# Save for fixing
with open('c:/Temp/MediCore/scripts/audit_results.json', 'w', encoding='utf-8') as f:
    json.dump(issues, f, ensure_ascii=False, indent=2)
print(f'\nRésultats sauvegardés dans scripts/audit_results.json')
