---
description: Modèle de données pharmacie. Tables, dimensions, faits, KPIs.
globs: "dbt/models/**/*.sql"
---

- 18 tables sources MySQL (winstat)
- 3 dimensions : `dim_pharmacie`, `dim_produit`, `dim_fournisseur`
- Surrogate keys via `ROW_NUMBER()` sur les dimensions
- Faits : ventes, commandes, ruptures, stock mouvements, stock valorisation
- KPIs : marge, écoulement, ABC (Pareto), ruptures, trésorerie
- Clés métier : `PHA_ID` (pharmacie), `PRD_ID` (produit), `FOU_ID` (fournisseur)
- Enrichissement produit : EAN13 + LPPR (codes pharmaceutiques)
- Star schema : faits -> LEFT JOIN -> dimensions
- Gestion des orphelins : `COALESCE(dim.sk, -1)` pour les FK manquantes
- Granularité temporelle : jour (`DBD_DATE`, `COM_DATE`, `FAC_DATE`)
- Volumétrie haute : COMMANDES, FACTURES, MODSTOCK, DAYBYDAY
- Préfixe colonnes source préservé dans staging
- Renommage métier dans marts uniquement
