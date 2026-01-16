### 📄 **ARCHITECTURE.md**

```markdown
# Architecture MediCore

## Flux de données global

Phase 1 : CDC CAPTURE (22h00)
┌─────────────────────┐
│ MySQL Winstat       │
│ (tables sources)    │
└──────────┬──────────┘
           │ (binlog)
           ↓
┌─────────────────────┐
│ cdc_ingestion.py    │
│ - Détecte CDC       │
│ - Applique masquage │
│ - Génère Parquet    │
└──────────┬──────────┘
           │
           ↓
[Fichiers Parquet]
(versionnés)

Phase 2 : LOAD (22h30)
┌──────────────────────┐
│ snowflake_loader.py  │
│ - Upload Parquet     │
│ - Crée staging tables│
│ - Enregistre audit   │
└──────────┬───────────┘
           │
           ↓
[Snowflake RAW]
(données brutes)

Phase 3 : TRANSFORM (23h00)
┌──────────────────────┐
│ dbt run              │
│ - Models (SQL)       │
│ - Tests (Quality)    │
│ - Docs (Lineage)     │
└──────────┬───────────┘
           │
           ↓
[Snowflake Marts]
(modèle sémantique)

Phase 4 : RECONCILIATION (23h30)
┌──────────────────────┐
│ reconciliation.py    │
│ - Vérifie checksums  │
│ - Compare volumes    │
│ - Alerte anomalies   │
└──────────────────────┘

## Layers Snowflake

### RAW Layer
- Données brutes depuis CDC
- Aucune transformation
- Historique complet (soft delete)
- Exemple : `RAW.RAW_pharmacie`

### STAGING Layer
- Nettoyage et normalisation
- Déduplication
- Suppression colonnes techniques
- Exemple : `STAGING.stg_pharmacie`

### MARTS Layer
- Modèle sémantique final
- Dimensions et faits (star schema)
- Optimisé pour requêtes analytiques
- Exemple : `MARTS.dim_pharmacie`

## Versioning

### CoreModel.xlsx
Version: 1.0.0 (sémantique)
Date: 2026-01-13
Contient:

Mapping sources → tables

Règles transformation

Règles masquage PII

v1.0.0-coremodel : Mapping
v1.0.0-pipeline : Scripts
v1.0.0-dbt : Modèles dbt


<u>Explication : Ce fichier décrit :</u>

Le flux global des données (4 phases)

L'organisation des données dans Snowflake (RAW/STAGING/MARTS)

La stratégie de versioning

Comment les composants s'intègrent





```
