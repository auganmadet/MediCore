"""Ajoute les blocs 'Référence KPIs' dans docs/06_Dashboards.md."""
import re

KPI_REFS = {
    "D1": "> **Référence KPIs** : §2.15 `mart_kpi_synthese_pharmacie` — CA, marge, taux générique, stock, dormants ([voir KPIs.md](KPIs.md#215-mart_kpi_synthese_pharmacie--vue-dashboard-consolidée))",
    "D2": "> **Référence KPIs** : §2.10 `mart_kpi_ca_evolution` — CA mensuel, YTD, 12DM, évolution vs A-1 ([voir KPIs.md](KPIs.md#210-mart_kpi_ca_evolution--évolution-ca-vs-a-1))",
    "D3": "> **Référence KPIs** : §2.5 `mart_kpi_tresorerie` + §1.6 `fact_tresorerie` — panier moyen, paiements, TVA, rétrocessions ([voir KPIs.md](KPIs.md#25-mart_kpi_tresorerie--trésorerie-mensuelle))",
    "D4": "> **Référence KPIs** : §2.1 `mart_kpi_marge` + §2.16 `mart_kpi_marge_par_produit` + §2.17 `mart_kpi_marge_par_univers` — marge par jour/produit/univers ([voir KPIs.md](KPIs.md#21-mart_kpi_marge--marge-journalière))",
    "D5": "> **Référence KPIs** : §2.8 `mart_kpi_operateur` — CA, panier, marge, productivité par vendeur ([voir KPIs.md](KPIs.md#28-mart_kpi_operateur--performance-opérateur))",
    "D6": "> **Référence KPIs** : §2.13 `mart_kpi_univers` — CA, marge, mix par univers RX/OTC/PARA ([voir KPIs.md](KPIs.md#213-mart_kpi_univers--kpis-par-univers-dashboard))",
    "D7": "> **Référence KPIs** : §2.2 `mart_kpi_stock` + §2.6 `mart_kpi_stock_valorisation` — rotation, couverture, valorisation ([voir KPIs.md](KPIs.md#22-mart_kpi_stock--rotation-et-rupture-stock-mensuelles))",
    "D8": "> **Référence KPIs** : §2.4 `mart_kpi_ruptures` + §2.18 `mart_kpi_ruptures_par_produit` — CA perdu, clients impactés, top produits ([voir KPIs.md](KPIs.md#24-mart_kpi_ruptures--impact-des-ruptures-et-ca-perdu))",
    "D9": "> **Référence KPIs** : §2.3 `mart_kpi_ecoulement` + §2.19 `mart_kpi_ecoulement_par_fournisseur` — taux d'écoulement produit et fournisseur ([voir KPIs.md](KPIs.md#23-mart_kpi_ecoulement--taux-découlement-mensuel))",
    "D10": "> **Référence KPIs** : §2.12 `mart_kpi_remise_labo` — remise pondérée, PDM achats, évolution vs A-1 ([voir KPIs.md](KPIs.md#212-mart_kpi_remise_labo--remise-pondérée-par-laboratoire))",
    "D11": "> **Référence KPIs** : §2.14 `mart_kpi_dormant` — capital immobilisé, dormants par univers/fournisseur ([voir KPIs.md](KPIs.md#214-mart_kpi_dormant--produits-sans-vente))",
    "D12": "> **Référence KPIs** : §2.9 `mart_kpi_abc` — classification Pareto, courbe ABC, top produits A ([voir KPIs.md](KPIs.md#29-mart_kpi_abc--classification-pareto))",
    "D13": "> **Référence KPIs** : §2.11 `mart_kpi_generique` + §2.21 `mart_kpi_generique_marge` — taux générique, PDM labo, marge gen. vs princeps ([voir KPIs.md](KPIs.md#211-mart_kpi_generique--génériques-et-parts-de-marché-labo))",
    "D14": "> **Référence KPIs** : §2.7 `mart_kpi_qualite_donnees` — fraîcheur, erreurs, taux pharmacies OK ([voir KPIs.md](KPIs.md#27-mart_kpi_qualite_donnees--monitoring-pipeline))",
    "D15": "> **Référence KPIs** : §1.1 `fact_ventes` + §1.2 `fact_commandes` + §2.20 `mart_kpi_ventes_par_produit` — ventes, commandes, profil client ([voir KPIs.md](KPIs.md#11-fact_ventes--ventes-quotidiennes))",
    "D16": "> **Référence KPIs** : §1.3 `fact_prix_journalier` + §1.4 `fact_stock_mouvement` — prix, marge unitaire, mouvements stock ([voir KPIs.md](KPIs.md#13-fact_prix_journalier--évolution-des-prix))",
}

with open('c:/Temp/MediCore/docs/06_Dashboards.md', 'r', encoding='utf-8') as f:
    content = f.read()

# For each dashboard, insert the KPI ref block before "#### Filtres"
# Strategy: find each "### Dx —" section, then find the next "#### Filtres" after it
for dx, ref_text in KPI_REFS.items():
    # Find the dashboard section header
    pattern = rf'(### {dx} —[^\n]*\n)'
    match = re.search(pattern, content)
    if not match:
        print(f'SKIP {dx}: section not found')
        continue

    start = match.start()

    # Find "#### Filtres" after this section (but before next ### section)
    filtres_pattern = r'#### Filtres'
    next_section = re.search(r'\n### ', content[start + 10:])
    end_boundary = start + 10 + next_section.start() if next_section else len(content)

    filtres_match = re.search(filtres_pattern, content[start:end_boundary])
    if not filtres_match:
        # D14 might not have "#### Filtres" - find "#### Disposition" instead
        filtres_match = re.search(r'#### Disposition', content[start:end_boundary])
        if not filtres_match:
            print(f'SKIP {dx}: no Filtres/Disposition section found')
            continue

    insert_pos = start + filtres_match.start()

    # Check if already has a KPI ref
    if 'Référence KPIs' in content[start:insert_pos]:
        print(f'SKIP {dx}: already has KPI ref')
        continue

    # Insert before "#### Filtres"
    content = content[:insert_pos] + ref_text + '\n\n' + content[insert_pos:]
    print(f'OK {dx}')

with open('c:/Temp/MediCore/docs/06_Dashboards.md', 'w', encoding='utf-8') as f:
    f.write(content)

print('\nDone')
