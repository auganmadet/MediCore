"""Corrige les cartes 369 et 405 : renomme template tag date -> mois.

Usage :
    python scripts/fix_cards_sql.py <session_token>
"""

import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print('Usage: python scripts/fix_cards_sql.py <token>')
    sys.exit(1)

TOKEN = sys.argv[1]
BASE = 'http://localhost:3001/api'


def api_get(path):
    req = urllib.request.Request(
        f'{BASE}/{path}',
        headers={'X-Metabase-Session': TOKEN},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def api_put(path, data):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{path}', data=body, method='PUT',
        headers={
            'X-Metabase-Session': TOKEN,
            'Content-Type': 'application/json; charset=utf-8',
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


# Card 369 : Distribution taux de marge
print('=== Card 369: Distribution taux de marge ===')
card = api_get('card/369')
dq = card['dataset_query']
fixed_sql = """
SELECT
    CASE
        WHEN TAUX_MARGE < 0 THEN '< 0%'
        WHEN TAUX_MARGE < 0.10 THEN '0-10%'
        WHEN TAUX_MARGE < 0.20 THEN '10-20%'
        WHEN TAUX_MARGE < 0.30 THEN '20-30%'
        WHEN TAUX_MARGE < 0.40 THEN '30-40%'
        WHEN TAUX_MARGE < 0.50 THEN '40-50%'
        ELSE '50%+'
    END AS tranche_marge,
    COUNT(*) AS nb_lignes
FROM MEDICORE_PROD.MARTS.MART_KPI_MARGE
WHERE 1=1
  [[AND PHARMACIE_SK = '{{pharmacie}}']]
  [[AND DATE_TRUNC('month', DATE_JOUR) = {{mois}}]]
GROUP BY 1 ORDER BY 1
"""
dq['stages'][0]['native'] = fixed_sql
dq['stages'][0]['template-tags'] = {
    'pharmacie': {
        'name': 'pharmacie',
        'display-name': 'Pharmacie',
        'type': 'text',
    },
    'mois': {
        'name': 'mois',
        'display-name': 'Mois',
        'type': 'date',
    },
}
api_put('card/369', {'dataset_query': dq})
print('  CORRIGEE')

# Card 405 : CA par tranche d'age
print('\n=== Card 405: CA par tranche d age ===')
card = api_get('card/405')
dq = card['dataset_query']
fixed_sql = """
SELECT
    CASE
        WHEN ORD_CLIENT_AGE_MONTHS IS NULL THEN 'Inconnu'
        WHEN ORD_CLIENT_AGE_MONTHS < 216 THEN '0-17 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 468 THEN '18-38 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 720 THEN '39-59 ans'
        WHEN ORD_CLIENT_AGE_MONTHS < 960 THEN '60-79 ans'
        ELSE '80+ ans'
    END AS tranche_age,
    SUM(CA_TTC) AS ca_ttc
FROM MEDICORE_PROD.MARTS.FACT_VENTES
WHERE 1=1
  [[AND PHARMACIE_SK = '{{pharmacie}}']]
  [[AND DATE_TRUNC('month', DATE_VENTE) = {{mois}}]]
GROUP BY 1
ORDER BY 2 DESC
"""
dq['stages'][0]['native'] = fixed_sql
dq['stages'][0]['template-tags'] = {
    'pharmacie': {
        'name': 'pharmacie',
        'display-name': 'Pharmacie',
        'type': 'text',
    },
    'mois': {
        'name': 'mois',
        'display-name': 'Mois',
        'type': 'date',
    },
}
api_put('card/405', {'dataset_query': dq})
print('  CORRIGEE')

print('\nTermine')
