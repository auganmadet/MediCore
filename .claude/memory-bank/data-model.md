# Data Model — MediCore ELT Pipeline

## Schéma Snowflake

### Couche RAW (18 tables)

Tables brutes, copie directe de MySQL avec métadonnées CDC.

#### 4 Tables CDC (temps réel via Kafka)

  ┌─────────────────┬──────────────────────────┬──────────────────────────┐
  │      Table      │       Clé primaire       │       Description        │
  ├─────────────────┼──────────────────────────┼──────────────────────────┤
  │ `RAW_COMMANDES` │ PHA_ID, COM_GROI, PRD_ID │ Commandes grossistes     │
  ├─────────────────┼──────────────────────────┼──────────────────────────┤
  │ `RAW_FACTURES`  │ PHA_ID, FAC_DATE, PRD_ID │ Factures/ventes          │
  ├─────────────────┼──────────────────────────┼──────────────────────────┤
  │ `RAW_ORDERS`    │ PHA_ID, ORD_ID           │ Commandes patients (PII) │
  ├─────────────────┼──────────────────────────┼──────────────────────────┤
  │ `RAW_MODSTOCK`  │ PHA_ID, MOD_DATE, PRD_ID │ Mouvements de stock      │
  └─────────────────┴──────────────────────────┴──────────────────────────┘

#### 14 Tables référence (bulk quotidien)

  ┌────────────────────┬──────────────────────────┬─────────────────────────┐
  │       Table        │       Clé primaire       │       Description       │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_DAYBYDAY`     │ PHA_ID, DBD_DATE, PRD_ID │ Données journalières    │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_EAN13`        │ EAN_CODE                 │ Codes-barres produits   │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_FOURNISSEURS` │ FOU_ID                   │ Fournisseurs            │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_HISTORY`      │ PHA_ID, HIS_DATE, PRD_ID │ Historique ventes       │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_LOG`          │ LOG_ID                   │ Logs système            │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_LPPR`         │ LPP_CODE                 │ Codes LPPR              │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_OPERATEUR`    │ OPE_ID                   │ Opérateurs              │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_PHARMACIE`    │ PHA_ID                   │ Pharmacies (PII)        │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_PRODUITS`     │ PRD_ID                   │ Produits                │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_QUANTHEB`     │ PHA_ID, QUA_DATE, PRD_ID │ Quantités hebdomadaires │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_REMISE`       │ REM_ID                   │ Remises                 │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_STOCK`        │ PHA_ID, PRD_ID           │ Stock courant           │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_TRESORERIE`   │ PHA_ID, TRE_DATE         │ Trésorerie              │
  ├────────────────────┼──────────────────────────┼─────────────────────────┤
  │ `RAW_VENTEPRD`     │ PHA_ID, VTE_DATE, PRD_ID │ Ventes produit          │
  └────────────────────┴──────────────────────────┴─────────────────────────┘

#### Colonnes CDC (ajoutées par le pipeline)

  ┌─────────────────┬───────────┬──────────────────────────────────────────────────────────┐
  │     Colonne     │   Type    │                       Description                        │
  ├─────────────────┼───────────┼──────────────────────────────────────────────────────────┤
  │ `cdc_operation` │ VARCHAR   │ `I` (insert), `U` (update), `D` (delete), `S` (snapshot) │
  ├─────────────────┼───────────┼──────────────────────────────────────────────────────────┤
  │ `cdc_timestamp` │ TIMESTAMP │ Horodatage de l'event                                    │
  ├─────────────────┼───────────┼──────────────────────────────────────────────────────────┤
  │ `cdc_schema`    │ VARCHAR   │ Schéma source                                            │
  ├─────────────────┼───────────┼──────────────────────────────────────────────────────────┤
  │ `cdc_table`     │ VARCHAR   │ Table source                                             │
  ├─────────────────┼───────────┼──────────────────────────────────────────────────────────┤
  │ `cdc_lsn`       │ VARCHAR   │ Log Sequence Number                                      │
  └─────────────────┴───────────┴──────────────────────────────────────────────────────────┘

### Couche STAGING (18 modèles)

Vues ou modèles incrémentaux avec déduplication CDC et masquage PII.

**Pattern standard staging** :
```sql
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

### Couche MARTS

#### 3 Dimensions

  ┌───────────────────┬──────────────────┬───────────────┬────────────────────────────────┐
  │      Modèle       │  Clé surrogate   │ Clé naturelle │          Description           │
  ├───────────────────┼──────────────────┼───────────────┼────────────────────────────────┤
  │ `dim_pharmacie`   │ `pharmacie_sk`   │ `PHA_ID`      │ Pharmacies (PII masqué)        │
  ├───────────────────┼──────────────────┼───────────────┼────────────────────────────────┤
  │ `dim_produit`     │ `produit_sk`     │ `PRD_ID`      │ Produits enrichis EAN13 + LPPR │
  ├───────────────────┼──────────────────┼───────────────┼────────────────────────────────┤
  │ `dim_fournisseur` │ `fournisseur_sk` │ `FOU_ID`      │ Fournisseurs                   │
  └───────────────────┴──────────────────┴───────────────┴────────────────────────────────┘

#### 8 Tables de faits

  ┌───────────────────────────┬──────────────────────────────────────────┬────────────────────┐
  │          Modèle           │                 Clés FK                  │    Description     │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_ventes`             │ pharmacie_sk, produit_sk                 │ Ventes agrégées    │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_commandes`          │ pharmacie_sk, produit_sk, fournisseur_sk │ Commandes          │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_ruptures`           │ pharmacie_sk, produit_sk                 │ Ruptures de stock  │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_stock_mouvement`    │ pharmacie_sk, produit_sk                 │ Mouvements stock   │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_stock_valorisation` │ pharmacie_sk, produit_sk                 │ Valorisation stock │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_prix_journalier`    │ pharmacie_sk, produit_sk                 │ Prix par jour      │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_operateur`          │ pharmacie_sk                             │ Opérations         │
  ├───────────────────────────┼──────────────────────────────────────────┼────────────────────┤
  │ `fact_tresorerie`         │ pharmacie_sk                             │ Trésorerie         │
  └───────────────────────────┴──────────────────────────────────────────┴────────────────────┘

#### KPIs métier

  ┌───────────────────────┬─────────────────────────────┐
  │        Modèle         │         Description         │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_ecoulement` │ Délai écoulement stock      │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_marge`      │ Marge par produit/pharmacie │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_abc`        │ Classification ABC (Pareto) │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_ruptures`   │ Taux de rupture             │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_stock`      │ Niveaux de stock            │
  ├───────────────────────┼─────────────────────────────┤
  │ `mart_kpi_tresorerie` │ Indicateurs trésorerie      │
  └───────────────────────┴─────────────────────────────┘

## Clés métier principales

  ┌────────────┬─────────────────────────┬─────────────┐
  │    Clé     │       Description       │   Format    │
  ├────────────┼─────────────────────────┼─────────────┤
  │ `PHA_ID`   │ Identifiant pharmacie   │ Integer     │
  ├────────────┼─────────────────────────┼─────────────┤
  │ `PRD_ID`   │ Identifiant produit     │ Integer     │
  ├────────────┼─────────────────────────┼─────────────┤
  │ `FOU_ID`   │ Identifiant fournisseur │ VARCHAR     │
  ├────────────┼─────────────────────────┼─────────────┤
  │ `EAN_CODE` │ Code-barres EAN13       │ VARCHAR(13) │
  ├────────────┼─────────────────────────┼─────────────┤
  │ `LPP_CODE` │ Code LPPR               │ VARCHAR     │
  └────────────┴─────────────────────────┴─────────────┘
