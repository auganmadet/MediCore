"""Corrige les noms (accents) et ajoute les descriptions des 97 cartes Metabase."""
import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = sys.argv[1]


def api_put(path, data):
    """Met à jour une ressource Metabase via PUT."""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:3000/api/' + path, data=body, method='PUT',
        headers={'X-Metabase-Session': TOKEN, 'Content-Type': 'application/json; charset=utf-8'}
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


# {card_id: (name, description)}
CARDS = {
    # D1 - Synthèse pharmacie
    353: ("Taux générique", "Taux de substitution générique vs objectif CPAM 80%"),
    354: ("Valeur stock PA", "Valeur du stock au prix d'achat"),
    356: ("Produits dormants 6m", "Nombre de produits sans vente depuis 6 mois"),
    355: ("Ratio stock/CA annuel", "Ratio entre la valeur du stock et le CA annualisé"),
    348: ("CA mensuel + évolution", "Chiffre d'affaires HT mensuel et évolution vs A-1"),
    349: ("CA YTD vs A-1", "Chiffre d'affaires cumulé depuis début d'année vs année précédente"),
    350: ("CA 12DM glissants", "Chiffre d'affaires sur les 12 derniers mois glissants"),
    351: ("Marge brute mensuelle", "Marge brute en euros par mois"),
    352: ("Taux de marge", "Taux de marge brute en pourcentage"),
    # D2 - Évolution CA
    38: ("CA mensuel N vs N-1", "Comparaison du CA HT mensuel année courante vs précédente"),
    39: ("Évolution YoY par mois", "Pourcentage d'évolution du CA mois par mois"),
    40: ("CA YTD cumulé N vs N-1", "CA cumulé depuis janvier, année courante vs précédente"),
    41: ("CA 12DM tendance lissée", "Tendance du CA sur 12 derniers mois glissants"),
    42: ("Jours de vente par mois", "Nombre de jours d'activité par mois"),
    # D3 - Trésorerie
    54: ("Points fidélité", "Total des points fidélité accordés"),
    57: ("Remises totales", "Montant total des remises accordées"),
    45: ("Panier moyen", "Montant moyen par transaction"),
    43: ("CA total mensuel", "Chiffre d'affaires total par mois"),
    47: ("Nb factures", "Nombre de factures émises"),
    49: ("Répartition modes de paiement", "Ventilation CB, espèces, chèques, tiers payant, virement"),
    51: ("Marge remb. vs non-remb.", "Marge sur produits remboursables vs non remboursables"),
    53: ("Rétrocessions", "Montant des rétrocessions"),
    366: ("TVA par taux", "Ventilation de la TVA par taux applicable"),
    # D4 - Marge détaillée
    62: ("Marge brute par jour", "Évolution de la marge brute quotidienne"),
    68: ("Marges négatives", "Produits vendus avec une marge négative"),
    367: ("Top 20 produits par marge", "Les 20 produits générant le plus de marge brute"),
    369: ("Distribution taux de marge", "Histogramme de répartition des taux de marge"),
    # D5 - Performance vendeurs
    80: ("Taux de marge par opérateur", "Taux de marge brute par vendeur"),
    88: ("Productivité CA moyen par jour", "CA moyen réalisé par jour et par opérateur"),
    77: ("Panier moyen par opérateur", "Montant moyen par transaction par vendeur"),
    73: ("CA par opérateur", "Chiffre d'affaires par vendeur"),
    91: ("Heure de pic CA par opérateur", "Heure de la journée avec le plus de CA par vendeur"),
    84: ("% lignes remboursables", "Part des lignes de vente remboursables par opérateur"),
    370: ("Nb clients/jour par opérateur", "Nombre moyen de clients servis par jour et par vendeur"),
    # D6 - Univers RX OTC PARA
    357: ("CA par univers", "Chiffre d'affaires par univers (RX, OTC, PARA)"),
    358: ("Taux de marge par univers", "Taux de marge brute par univers"),
    359: ("Mix CA (% par univers)", "Répartition du CA en pourcentage par univers"),
    360: ("Mix marge (% par univers)", "Répartition de la marge en pourcentage par univers"),
    361: ("Évolution CA vs A-1 par univers", "Évolution du CA par univers vs année précédente"),
    # D7 - Stock et rotation
    97: ("Rotation stock mensuelle", "Nombre de rotations du stock par mois"),
    100: ("Taux de rupture stock", "Pourcentage de produits en rupture de stock"),
    104: ("Valorisation stock PA fin mois", "Valeur du stock au prix d'achat en fin de mois"),
    108: ("Couverture stock en jours", "Nombre de jours de vente couverts par le stock"),
    112: ("Marge latente moyenne", "Marge potentielle moyenne sur le stock"),
    371: ("Stock moyen vs ventes", "Comparaison stock moyen et quantités vendues"),
    372: ("Variation prix d'achat", "Évolution des prix d'achat (détection inflation)"),
    # D8 - Ruptures et CA perdu
    117: ("CA estimé perdu par mois", "Chiffre d'affaires perdu à cause des ruptures"),
    120: ("Marge estimée perdue", "Marge perdue à cause des ruptures de stock"),
    124: ("Clients impactés par mois", "Nombre de clients affectés par les ruptures"),
    128: ("Taux de rupture demande", "Pourcentage de demandes non satisfaites"),
    373: ("Top 10 produits en rupture", "Les 10 produits avec le plus de ruptures"),
    374: ("Jours de rupture par produit", "Nombre de jours en rupture par produit"),
    # D9 - Écoulement
    140: ("Produits sur-stockés (taux < 50%)", "Produits avec un taux d'écoulement inférieur à 50%"),
    134: ("Taux d'écoulement mensuel", "Taux d'écoulement global par mois"),
    136: ("Commandé vs vendu par mois", "Comparaison quantités commandées et vendues"),
    384: ("Écoulement par fournisseur", "Taux d'écoulement moyen par fournisseur"),
    # D10 - Remises fournisseurs
    362: ("Remise pondérée par labo", "Remise pondérée par les quantités pour chaque laboratoire"),
    363: ("PDM achats par labo", "Part de marché en achats par laboratoire"),
    364: ("Remise simple vs pondérée", "Comparaison remise moyenne et remise pondérée"),
    365: ("Évolution remise vs A-1", "Évolution des remises vs année précédente par labo"),
    385: ("Montant achats par labo + évolution", "Montant total des achats et évolution vs A-1"),
    # D11 - Produits dormants
    164: ("Top 20 dormants par valeur", "Les 20 produits dormants avec la plus grande valeur en stock"),
    151: ("Nb produits dormants 6m", "Nombre de produits sans vente depuis 6 mois"),
    160: ("Dormants par univers", "Répartition des dormants par univers"),
    154: ("Marge latente bloquée", "Marge potentielle immobilisée dans les stocks dormants"),
    156: ("Répartition par statut dormant", "Ventilation des produits par statut de dormance"),
    147: ("Capital immobilisé (dormants 6m)", "Valeur du stock immobilisé dans les produits dormants"),
    386: ("Dormants par fournisseur", "Nombre de produits dormants par fournisseur"),
    # D12 - Classification ABC
    176: ("Courbe de Pareto (% CA cumulé)", "Courbe ABC : pourcentage du CA cumulé par produit"),
    173: ("CA par classe ABC", "Chiffre d'affaires par classe A, B ou C"),
    170: ("Répartition A / B / C", "Nombre de produits par classe ABC"),
    180: ("Top 10 produits A", "Les 10 premiers produits de la classe A"),
    400: ("Nb produits classe B", "Nombre de produits en classe B"),
    401: ("Nb produits classe C", "Nombre de produits en classe C"),
    387: ("Nb produits classe A", "Nombre de produits en classe A"),
    # D13 - Génériques et labos
    186: ("Taux générique pharmacie", "Taux de substitution générique de la pharmacie"),
    189: ("CA générique vs princeps", "CA des génériques comparé aux princeps"),
    192: ("PDM par labo (top 15)", "Part de marché des 15 premiers laboratoires"),
    196: ("Nb produits par labo", "Nombre de produits référencés par laboratoire"),
    200: ("Évolution CA par labo vs A-1", "Évolution du CA par laboratoire vs année précédente"),
    402: ("Marge générique vs princeps", "Comparaison du taux de marge génériques vs princeps"),
    # D14 - Qualité des données
    205: ("Taux pharmacies OK", "Pourcentage de pharmacies avec données à jour"),
    208: ("Nb erreurs total", "Nombre total d'erreurs détectées"),
    212: ("Répartition OK / Alerte / Critique", "Ventilation des pharmacies par statut de fraîcheur"),
    216: ("Fraîcheur par pharmacie", "Statut de fraîcheur des données par pharmacie"),
    220: ("Erreurs récentes", "Liste des erreurs les plus récentes"),
    403: ("Nb pharmacies en alerte", "Nombre de pharmacies en statut alerte ou critique"),
    # D15 - Détail transactions
    227: ("Ventes par jour", "Détail des ventes quotidiennes"),
    236: ("Ventes par sexe", "Répartition des ventes par sexe du client"),
    241: ("Commandes par fournisseur", "Volume de commandes par fournisseur"),
    404: ("Top produits vendus", "Les produits les plus vendus en quantité"),
    405: ("CA par tranche d'âge", "Chiffre d'affaires par tranche d'âge client"),
    # D16 - Prix et mouvements stock
    249: ("Évolution prix (tarif, public, achat net)", "Évolution des prix tarif, public et achat net d'un produit"),
    251: ("Marge brute unitaire", "Évolution de la marge brute par unité"),
    256: ("Mouvements stock par jour", "Entrées et sorties de stock quotidiennes"),
    261: ("Type opération stock", "Répartition par type d'opération de stock"),
    406: ("Niveau stock après mouvement", "Niveau de stock après chaque mouvement"),
}

count = 0
errors = 0
for cid, (name, desc) in CARDS.items():
    try:
        api_put(f'card/{cid}', {'name': name, 'description': desc})
        count += 1
        if count % 10 == 0:
            print(f'{count} cartes traitées...')
    except Exception as e:
        errors += 1
        print(f'Erreur carte {cid}: {e}')

print(f'Terminé : {count}/{len(CARDS)} cartes corrigées, {errors} erreurs')
