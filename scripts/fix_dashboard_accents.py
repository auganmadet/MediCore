"""Corrige les noms et descriptions des 16 dashboards Metabase (accents)."""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = sys.argv[1]


def api_put(path, data):
    """Met à jour une ressource Metabase via PUT."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:3001/api/' + path, data=body, method='PUT',
        headers={'X-Metabase-Session': TOKEN, 'Content-Type': 'application/json; charset=utf-8'}
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


# {dashboard_id: (name, description)}
DASHBOARDS = {
    2:  ("D1 - Synthèse pharmacie",
         "Vue d'ensemble : CA, marge, taux générique, stock dormant"),
    3:  ("D2 - Évolution CA",
         "Progression CA vs A-1, YTD, 12DM"),
    4:  ("D3 - Trésorerie",
         "Cash-flow, modes de paiement, marge remb. vs non-remb."),
    5:  ("D4 - Marge détaillée",
         "Top produits par marge, marges négatives, taux par univers"),
    6:  ("D5 - Performance vendeurs",
         "CA, panier moyen, taux marge, heure pic par opérateur"),
    7:  ("D6 - Univers RX OTC PARA",
         "Mix CA et marge par univers, évolution vs A-1"),
    8:  ("D7 - Stock et rotation",
         "Rotation, couverture jours, valorisation PA vs PV"),
    9:  ("D8 - Ruptures et CA perdu",
         "CA estimé perdu, clients impactés, top produits rupture"),
    10: ("D9 - Écoulement",
         "Taux d'écoulement, produits sur-stockés, écoulement par fournisseur"),
    11: ("D10 - Remises fournisseurs",
         "Remise pondérée par labo, PDM achats, évolution vs A-1"),
    12: ("D11 - Produits dormants",
         "Capital immobilisé, dormants par fournisseur et univers"),
    13: ("D12 - Classification ABC",
         "Courbe Pareto, répartition A B C, top 10 produits A"),
    14: ("D13 - Génériques et labos",
         "Taux générique vs CPAM 80%, PDM par labo"),
    15: ("D14 - Qualité des données",
         "Fraîcheur pharmacies, erreurs récentes, taux OK"),
    16: ("D15 - Détail transactions",
         "Ventes par jour, top produits, profil clientèle"),
    17: ("D16 - Prix et mouvements stock",
         "Évolution prix d'achat, mouvements stock, type opération"),
}

count = 0
for did, (name, desc) in DASHBOARDS.items():
    try:
        api_put(f'dashboard/{did}', {'name': name, 'description': desc})
        count += 1
        print(f'Dashboard {did}: {name}')
    except Exception as e:
        print(f'Erreur dashboard {did}: {e}')

print(f'\nTerminé : {count}/{len(DASHBOARDS)} dashboards corrigés')
