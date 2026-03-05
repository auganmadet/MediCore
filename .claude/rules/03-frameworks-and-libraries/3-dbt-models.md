---
description: Patterns dbt pour les modèles staging, marts, snapshots et hooks. Incremental, merge, macros, tags.
globs: "dbt/**/*.sql,dbt/**/*.yml"
---

- Staging : `materialized='incremental'` avec `incremental_strategy='merge'`
- Staging : `unique_key` = clé primaire composite de la table source
- Staging : filtre `WHERE cdc_operation != 'D'` pour exclure les deletes
- Staging : dédup via `ROW_NUMBER() OVER (PARTITION BY PK ORDER BY cdc_timestamp DESC)`
- Marts dimensions : surrogate keys via `ROW_NUMBER()`
- Marts faits : agrégations par clés métier (pharmacie, produit, date)
- Marts KPIs : calculs métier (marge, écoulement, ABC, ruptures)
- LEFT JOIN sur les dimensions pour gérer les orphelins
- `{{ source('mysql_raw', 'RAW_XXX') }}` pour toutes les sources
- `{{ ref('stg_xxx') }}` pour les références staging -> marts
- `{{ mask_pii('column') }}` pour le masquage PII en staging
- Tests dans `_staging.yml` et `_marts.yml` : `not_null`, `unique`, `relationships`
- Tags : `['staging', 'table_name']` ou `['marts', 'table_name']`
- Schéma explicite dans config : `STAGING` ou `MARTS`
- Snapshots SCD2 : `strategy='check'`, `check_cols` sur les colonnes métier susceptibles de changer
- Snapshots : `target_schema='SNAPSHOTS'` systématiquement
- Snapshots : `unique_key` composite pour les tables multi-pharmacie : `"PHA_ID || '-' || FK_ID"`
- Snapshots : sélectionner depuis `{{ ref('stg_xxx') }}`, jamais depuis RAW directement
- Hook `on-run-end` : résumé Teams (warnings, erreurs, nombre de modèles) — ne jamais mettre de logique métier dans les hooks, réservé au monitoring
