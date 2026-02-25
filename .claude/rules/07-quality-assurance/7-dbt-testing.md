---
description: Conventions de test dbt et qualité des données. Tests schéma, freshness, data quality.
globs: "dbt/**/*.yml,dbt/**/*.sql"
---

- Tests définis dans `_staging.yml` et `_marts.yml`
- `not_null` sur toutes les clés primaires et champs obligatoires
- `unique` sur les clés primaires et surrogate keys
- `relationships` entre faits et dimensions (FK integrity)
- `accepted_values` pour les champs énumérés (opérations CDC)
- Source freshness dans `sources.yml`
- CDC : `warn_after: 12 hours`, `error_after: 24 hours`
- Référence : `warn_after: 36 hours`, `error_after: 48 hours`
- `dbt test --select stg_*` après chaque run staging
- `dbt source freshness` dans la boucle batch
- Alertes Teams webhook sur échecs de tests
- Tests prioritaires : ventes, commandes, stock, PII masking
- Valider la déduplication CDC (pas de doublons sur PK)
- Valider le masquage PII (aucun nom/adresse en clair dans staging)
