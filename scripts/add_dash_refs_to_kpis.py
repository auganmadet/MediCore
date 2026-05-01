"""Ajoute les blocs 'Dashboard' dans docs/05_KPIs.md pour chaque modèle."""
import re

# Mapping: section header pattern -> dashboard reference
DASH_REFS = {
    "### 2.1 mart_kpi_marge": "> **Dashboard** : [D4 — Marge détaillée](Dashboards.md#d4--marge-détaillée) — Marge brute par jour, distribution taux de marge",
    "### 2.2 mart_kpi_stock": "> **Dashboard** : [D7 — Stock et rotation](Dashboards.md#d7--stock-et-rotation) — Rotation stock, taux de rupture, stock moyen vs ventes",
    "### 2.3 mart_kpi_ecoulement": "> **Dashboard** : [D9 — Écoulement](Dashboards.md#d9--écoulement-sell-through) — Taux d'écoulement mensuel, commandé vs vendu, produits sur-stockés",
    "### 2.4 mart_kpi_ruptures —": "> **Dashboard** : [D8 — Ruptures et CA perdu](Dashboards.md#d8--ruptures-et-ca-perdu) — CA estimé perdu, marge perdue, clients impactés, taux de rupture",
    "### 2.5 mart_kpi_tresorerie": "> **Dashboard** : [D3 — Trésorerie](Dashboards.md#d3--trésorerie) — CA total, panier moyen, nb factures, modes de paiement, rétrocessions",
    "### 2.6 mart_kpi_stock_valorisation": "> **Dashboard** : [D7 — Stock et rotation](Dashboards.md#d7--stock-et-rotation) — Valorisation PA fin mois, couverture en jours, marge latente",
    "### 2.7 mart_kpi_qualite_donnees": "> **Dashboard** : [D14 — Qualité des données](Dashboards.md#d14--qualité-des-données) — Taux pharmacies OK, erreurs, fraîcheur",
    "### 2.8 mart_kpi_operateur": "> **Dashboard** : [D5 — Performance vendeurs](Dashboards.md#d5--performance-vendeurs) — CA, panier moyen, taux marge, productivité par opérateur",
    "### 2.9 mart_kpi_abc": "> **Dashboard** : [D12 — Classification ABC](Dashboards.md#d12--classification-abc-pareto) — Courbe Pareto, répartition A/B/C, top 10 produits A",
    "### 2.10 mart_kpi_ca_evolution": "> **Dashboard** : [D2 — Évolution CA](Dashboards.md#d2--évolution-ca) — CA mensuel N vs N-1, YTD, 12DM, jours de vente",
    "### 2.11 mart_kpi_generique —": "> **Dashboard** : [D13 — Génériques et labos](Dashboards.md#d13--génériques-et-labos) — Taux générique, PDM par labo, nb produits par labo",
    "### 2.12 mart_kpi_remise_labo": "> **Dashboard** : [D10 — Remises fournisseurs](Dashboards.md#d10--remises-fournisseurs) — Remise pondérée, PDM achats, évolution vs A-1",
    "### 2.13 mart_kpi_univers": "> **Dashboard** : [D6 — Univers RX OTC PARA](Dashboards.md#d6--univers-rxotcpara) — CA, marge, mix par univers",
    "### 2.14 mart_kpi_dormant": "> **Dashboard** : [D11 — Produits dormants](Dashboards.md#4-d11--produits-dormants-exemple-détaillé) — Capital immobilisé, dormants par univers/fournisseur",
    "### 2.15 mart_kpi_synthese_pharmacie": "> **Dashboard** : [D1 — Synthèse pharmacie](Dashboards.md#d1--vue-densemble-pharmacie) — Vue exécutive : CA, marge, stock, dormants, générique",
    "### 2.16 mart_kpi_marge_par_produit": "> **Dashboard** : [D4 — Marge détaillée](Dashboards.md#d4--marge-détaillée) — Top 20 produits par marge",
    "### 2.17 mart_kpi_marge_par_univers": "> **Dashboard** : [D4 — Marge détaillée](Dashboards.md#d4--marge-détaillée) — Taux de marge par univers",
    "### 2.18 mart_kpi_ruptures_par_produit": "> **Dashboard** : [D8 — Ruptures et CA perdu](Dashboards.md#d8--ruptures-et-ca-perdu) — Top 10 produits en rupture, jours de rupture par produit",
    "### 2.19 mart_kpi_ecoulement_par_fournisseur": "> **Dashboard** : [D9 — Écoulement](Dashboards.md#d9--écoulement-sell-through) — Écoulement par fournisseur",
    "### 2.20 mart_kpi_ventes_par_produit": "> **Dashboard** : [D15 — Détail transactions](Dashboards.md#d15--détail-transactions-drill-down) — Top produits vendus",
    "### 2.21 mart_kpi_generique_marge": "> **Dashboard** : [D13 — Génériques et labos](Dashboards.md#d13--génériques-et-labos) — Marge générique vs princeps",
}

# Also add refs for fact tables (section 1.x)
FACT_REFS = {
    "### 1.1 fact_ventes": "> **Dashboard** : [D15 — Détail transactions](Dashboards.md#d15--détail-transactions-drill-down) — Ventes par jour, ventes par sexe, CA par tranche d'âge",
    "### 1.2 fact_commandes": "> **Dashboard** : [D15 — Détail transactions](Dashboards.md#d15--détail-transactions-drill-down) — Commandes par fournisseur",
    "### 1.3 fact_prix_journalier": "> **Dashboard** : [D16 — Prix et mouvements stock](Dashboards.md#d16--prix-et-mouvements-stock) — Évolution prix tarif/public/achat, marge brute unitaire",
    "### 1.4 fact_stock_mouvement": "> **Dashboard** : [D16 — Prix et mouvements stock](Dashboards.md#d16--prix-et-mouvements-stock) — Mouvements stock par jour, type opération, niveau stock",
    "### 1.5 fact_ruptures": "> **Dashboard** : [D8 — Ruptures et CA perdu](Dashboards.md#d8--ruptures-et-ca-perdu) — Données source pour mart_kpi_ruptures",
    "### 1.6 fact_tresorerie": "> **Dashboard** : [D3 — Trésorerie](Dashboards.md#d3--trésorerie) — TVA par taux, répartition modes de paiement",
    "### 1.7 fact_stock_valorisation": "> **Dashboard** : [D7 — Stock et rotation](Dashboards.md#d7--stock-et-rotation) — Données source pour mart_kpi_stock_valorisation",
    "### 1.8 fact_operateur": "> **Dashboard** : [D5 — Performance vendeurs](Dashboards.md#d5--performance-vendeurs) — Données source pour mart_kpi_operateur",
}

ALL_REFS = {**DASH_REFS, **FACT_REFS}

with open('c:/Temp/MediCore/docs/05_KPIs.md', 'r', encoding='utf-8') as f:
    content = f.read()

count = 0
for header, ref_text in ALL_REFS.items():
    # Find the header
    idx = content.find(header)
    if idx == -1:
        print(f'SKIP: {header} not found')
        continue

    # Check if already has Dashboard ref nearby (within 500 chars after header)
    nearby = content[idx:idx + 500]
    if '**Dashboard**' in nearby:
        print(f'SKIP: {header} already has Dashboard ref')
        continue

    # Find the next blank line after the header (end of header line)
    header_end = content.find('\n', idx)
    next_line_start = header_end + 1

    # Insert the ref right after the header line
    content = content[:next_line_start] + '\n' + ref_text + '\n' + content[next_line_start:]
    count += 1
    print(f'OK: {header}')

with open('c:/Temp/MediCore/docs/05_KPIs.md', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone: {count} références ajoutées')
