# dbt Transformations — MediCore ELT Pipeline

## Configuration dbt

- **Projet** : `medicore` (dbt_project.yml)
- **Profil** : `medicore` (profiles.yml)
- **Packages** : `dbt_utils` (packages.yml)
- **Target dev** : `MEDIcore_WH` (XS), schéma suffixé `_DEV`
- **Target prod** : `MEDIcore_WH` (XL), schémas `STAGING`/`MARTS`

## Modèles staging (18)

**Matérialisation** : `incremental` avec `merge` strategy

**Pattern standard** :
```sql
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PK_COL1', 'PK_COL2'],
    schema='STAGING',
    tags=['staging', 'table_name', 'high_volume', 'incremental']
) }}
{{ guard_full_refresh() }}

WITH source_data AS (
    SELECT * FROM {{ source('mysql_raw', 'RAW_XXX') }}
    WHERE cdc_operation != 'D'
    {% if is_incremental() %}
      AND cdc_timestamp >= (SELECT COALESCE(MAX(loaded_at), '1900-01-01') FROM {{ this }})
    {% endif %}
),
dedup_cdc AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY PK_COLUMNS
            ORDER BY cdc_timestamp DESC NULLS LAST
        ) AS rn
    FROM source_data
)
SELECT columns, cdc_timestamp AS loaded_at
FROM dedup_cdc WHERE rn = 1
```

**Transformations staging** :
- Dédup CDC : `ROW_NUMBER()` sur PK + `ORDER BY cdc_timestamp DESC`
- Filtre deletes : `WHERE cdc_operation != 'D'`
- PII masking : `{{ mask_pii('nom_pharmacie') }}` -> MD5
- Type casting : `upper(trim(FOU_ID))`
- Renommage : `cdc_timestamp AS loaded_at`

## Modèles marts

### Dimensions (3)

  ┌───────────────────┬──────────────────┬───────────────────────────────────────────┐
  │      Modèle       │  Clé surrogate   │              Source staging               │
  ├───────────────────┼──────────────────┼───────────────────────────────────────────┤
  │ `dim_pharmacie`   │ `pharmacie_sk`   │ `stg_pharmacie`                           │
  ├───────────────────┼──────────────────┼───────────────────────────────────────────┤
  │ `dim_produit`     │ `produit_sk`     │ `stg_produits` + `stg_ean13` + `stg_lppr` │
  ├───────────────────┼──────────────────┼───────────────────────────────────────────┤
  │ `dim_fournisseur` │ `fournisseur_sk` │ `stg_fournisseurs`                        │
  └───────────────────┴──────────────────┴───────────────────────────────────────────┘

**Pattern dimension** : `ROW_NUMBER() OVER (ORDER BY natural_key)` pour surrogate key

### Faits (8)

Jointures LEFT JOIN vers dimensions, `COALESCE(dim.sk, -1)` pour orphelins.

### KPIs métier

Calculs agrégés sur les faits, documentés dans `docs/KPIs.md`.

## Macros

### `pii_masking.sql`

```sql
{% macro mask_pii(column_name) %}
    MD5(CAST({{ column_name }} AS VARCHAR))
{% endmacro %}

{% macro guard_full_refresh() %}
    {% if flags.FULL_REFRESH %}
        {{ exceptions.raise_compiler_error("FULL_REFRESH interdit sur ce modèle") }}
    {% endif %}
{% endmacro %}
```

## Tests dbt

### Fichiers de tests
- `_staging.yml` : tests sur modèles staging
- `_marts.yml` : tests sur modèles marts

### Types de tests
- `not_null` : clés primaires, champs obligatoires
- `unique` : clés primaires, surrogate keys
- `relationships` : FK entre faits et dimensions
- `accepted_values` : énumérations (opérations CDC)

### Freshness (sources.yml)
- CDC : `warn_after: {count: 12, period: hour}`, `error_after: {count: 24, period: hour}`
- Référence : `warn_after: {count: 36, period: hour}`, `error_after: {count: 48, period: hour}`

## Commandes dbt courantes

```bash
dbt run --select tag:staging          # Tous les modèles staging
dbt run --select tag:marts            # Tous les modèles marts
dbt run --select stg_commandes        # Un modèle spécifique
dbt run --select +fact_ventes         # Modèle + ses dépendances
dbt test --select stg_*               # Tests staging
dbt test --select _marts              # Tests marts
dbt source freshness                  # Fraîcheur des sources
dbt debug                             # Diagnostic connexion
dbt deps                              # Installer packages
```
