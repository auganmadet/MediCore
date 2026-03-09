# dbt Transformations — MediCore ELT Pipeline

## Configuration dbt

- **Projet** : `medicore` (dbt_project.yml)
- **Profil** : `medicore` (profiles.yml)
- **Packages** : `dbt_utils` 1.3.0 (pin exact dans packages.yml)
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

Jointures LEFT JOIN vers les 3 dimensions. Pattern orphelin : `COALESCE(dim.sk, md5('-1'))` pour
les FK sans correspondance (pharmacie, produit, fournisseur). Chaque dimension contient une ligne
orpheline (`-1`, `'INCONNU'`) via `UNION ALL`.

### KPIs métier (15)

**Matérialisation mixte** : incremental (11) + table (4)

#### Marts incremental (merge 2 derniers mois)

| Mart | Clé unique | Grain |
|------|------------|-------|
| `mart_kpi_abc` | pharmacie_sk, produit_sk, mois | Produit/mois |
| `mart_kpi_ecoulement` | pharmacie_sk, produit_sk, mois | Produit/mois |
| `mart_kpi_generique` | pharmacie_sk, mois, FOU_ID, is_generique, univers | Labo/mois |
| `mart_kpi_marge` | pharmacie_sk, produit_sk, date_jour | Produit/jour |
| `mart_kpi_operateur` | pharmacie_sk, operateur, mois | Opérateur/mois |
| `mart_kpi_remise_labo` | pharmacie_sk, fournisseur_sk, mois | Labo/mois |
| `mart_kpi_ruptures` | pharmacie_sk, produit_sk, mois | Produit/mois |
| `mart_kpi_stock` | pharmacie_sk, produit_sk, mois | Produit/mois |
| `mart_kpi_stock_valorisation` | pharmacie_sk, produit_sk, mois | Produit/mois |
| `mart_kpi_tresorerie` | pharmacie_sk, mois | Pharmacie/mois |
| `mart_kpi_univers` | pharmacie_sk, mois, univers | Univers/mois |

#### Marts table (full refresh obligatoire)

| Mart | Raison |
|------|--------|
| `mart_kpi_dormant` | Utilise `current_date()` — état changeant quotidiennement |
| `mart_kpi_qualite_donnees` | Utilise `current_timestamp()` — fraîcheur temps réel |
| `mart_kpi_ca_evolution` | Calculs YTD et 12DM rolling — historique complet requis |
| `mart_kpi_synthese_pharmacie` | Agrège depuis marts non-incrémentaux |

Calculs agrégés sur les faits, documentés dans `docs/KPIs.md`.

## Macros

### `pii_masking.sql` — `pii_mask(column_name, prefix, hash_length=4)`

Masquage PII centralisé. Génère `'PREFIX_' || LEFT(MD5(CAST(col AS VARCHAR)), 4)`.

```sql
{% macro pii_mask(column_name, prefix, hash_length=4) %}
'{{ prefix }}_' || LEFT(MD5(CAST({{ column_name }} AS VARCHAR)), {{ hash_length }})
{% endmacro %}
```

Utilisé dans : `stg_fournisseurs`, `stg_pharmacie`, `stg_pharmacies`, `stg_orders`, `stg_mediprix_factures`.

### `guard_full_refresh.sql`

Protège les modèles tagués `high_volume` contre un full-refresh accidentel.
Bloque avec erreur explicite sauf si `--vars '{allow_full_refresh: true}'` est passé.

```
Bypass : dbt run --full-refresh --vars '{allow_full_refresh: true}' --select <model>
```

Utilisé dans : `fact_commandes`, `fact_operateur`, `fact_prix_journalier`,
`fact_stock_mouvement`, `fact_stock_valorisation`, `fact_ventes`.

## Tests dbt

### Fichiers de tests
- `_staging.yml` : tests sur modèles staging
- `_marts.yml` : tests sur modèles marts
- `_audit.yml` : tests sur modèles audit (audit_run_summary, audit_dbt_summary, audit_latest_runs)
- `_snapshots.yml` : tests sur snapshots SCD2 (snap_pharmacie, snap_produit, snap_fournisseur)
- `sources.yml` : tests accepted_values sur cdc_operation (C, U, D, R) pour 4 tables CDC

### Types de tests
- `not_null` : clés primaires, champs obligatoires
- `unique` : clés primaires, surrogate keys
- `relationships` : FK entre faits et dimensions
- `accepted_values` : énumérations (opérations CDC : C, U, D, R)
- `dbt_utils.expression_is_true` : prix/montants >= 0 (severity: warn) — systématisé sur toutes les colonnes prix/montants des facts et dimensions

### Freshness (sources.yml)
- CDC : `warn_after: {count: 12, period: hour}`, `error_after: {count: 24, period: hour}`
- Référence : `warn_after: {count: 36, period: hour}`, `error_after: {count: 48, period: hour}`

## Commandes dbt courantes

```bash
# === RUNS QUOTIDIENS ===
dbt run --select tag:staging          # Tous les modèles staging
dbt run --select tag:marts            # Tous les modèles marts
dbt run --select tag:kpi              # Tous les marts KPI (incremental)

# === INITIALISATION / REFRESH MENSUEL ===
dbt run --select tag:kpi --full-refresh   # Full refresh marts KPI (à faire 1x/mois)

# === MODÈLES SPÉCIFIQUES ===
dbt run --select stg_commandes        # Un modèle spécifique
dbt run --select +fact_ventes         # Modèle + ses dépendances

# === TESTS ===
dbt test --select stg_*               # Tests staging
dbt test --select _marts              # Tests marts

# === MAINTENANCE ===
dbt source freshness                  # Vérifier fraîcheur des sources
dbt debug                             # Diagnostic connexion
dbt deps                              # Installer packages
```

## Snapshots (SCD Type 2)

3 snapshots dans `dbt/snapshots/`, strategy `check`, target schema `SNAPSHOTS`.
Documentation et tests dans `_snapshots.yml`.

  ┌────────────────────┬──────────────────────────┬──────────────────────────────────────────────────┐
  │      Snapshot       │        Unique key        │                   Check cols                     │
  ├────────────────────┼──────────────────────────┼──────────────────────────────────────────────────┤
  │ `snap_pharmacie`   │ `PHA_ID`                 │ PHA_NOM, PHA_GERS, PHA_DATE_INSTAL_WP            │
  ├────────────────────┼──────────────────────────┼──────────────────────────────────────────────────┤
  │ `snap_produit`     │ `PHA_ID \|\| '-' \|\| PRD_ID` │ PRD_NOM, PRD_CODEREMBT, PRD_CODEACTE, PRD_TVA, FOU_ID │
  ├────────────────────┼──────────────────────────┼──────────────────────────────────────────────────┤
  │ `snap_fournisseur` │ `PHA_ID \|\| '-' \|\| FOU_ID` │ FOU_NOM, FOU_TYPE, FOU_REPARTITEUR, FOU_ADRESSE, FOU_CP, FOU_VILLE │
  └────────────────────┴──────────────────────────┴──────────────────────────────────────────────────┘
