---
description: Conventions de test dbt et qualite des donnees. Tests schema, freshness, data quality.
globs: "dbt/**/*.yml,dbt/**/*.sql"
---

- Tests definis dans `_staging.yml` et `_marts.yml`
- `not_null` sur toutes les cles primaires et champs obligatoires
- `unique` sur les cles primaires et surrogate keys
- `relationships` entre faits et dimensions (FK integrity)
- `accepted_values` pour les champs enumeres (operations CDC)
- Source freshness dans `sources.yml`
- CDC : `warn_after: 12 hours`, `error_after: 24 hours`
- Reference : `warn_after: 36 hours`, `error_after: 48 hours`
- `dbt test --select stg_*` apres chaque run staging
- `dbt source freshness` dans la boucle batch
- Alertes Teams webhook sur echecs de tests
- Tests prioritaires : ventes, commandes, stock, PII masking
- Valider la deduplication CDC (pas de doublons sur PK)
- Valider le masquage PII (aucun nom/adresse en clair dans staging)
