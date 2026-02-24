---
description: Patterns dbt pour les modeles staging et marts. Incremental, merge, macros, tags.
globs: "dbt/**/*.sql,dbt/**/*.yml"
---

- Staging : `materialized='incremental'` avec `incremental_strategy='merge'`
- Staging : `unique_key` = cle primaire composite de la table source
- Staging : filtre `WHERE cdc_operation != 'D'` pour exclure les deletes
- Staging : dedup via `ROW_NUMBER() OVER (PARTITION BY PK ORDER BY cdc_timestamp DESC)`
- Marts dimensions : surrogate keys via `ROW_NUMBER()`
- Marts faits : aggregations par cles metier (pharmacie, produit, date)
- Marts KPIs : calculs metier (marge, ecoulement, ABC, ruptures)
- LEFT JOIN sur les dimensions pour gerer les orphelins
- `{{ source('mysql_raw', 'RAW_XXX') }}` pour toutes les sources
- `{{ ref('stg_xxx') }}` pour les references staging -> marts
- `{{ mask_pii('column') }}` pour le masquage PII en staging
- Tests dans `_staging.yml` et `_marts.yml` : `not_null`, `unique`, `relationships`
- Tags : `['staging', 'table_name']` ou `['marts', 'table_name']`
- Schema explicite dans config : `STAGING` ou `MARTS`
