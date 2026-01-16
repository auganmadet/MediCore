# 🏥 MediCore - ELT Pipeline pour Data Warehouse Pharmacie
**Framework d'ingestion de données MEDIPRIX permettant une industrialisation complète avec audit et gouvernance.**

## Vision
MediCore est un pipeline ELT (Extract-Load-Transform) industrialisé pour ingérer 
les données pharmaceutiques depuis MySQL Winstat vers Snowflake avec :
- Change Data Capture (CDC) pour temps quasi-réel
- Masquage automatique des données sensibles (PII)
- Data lineage et audit complet
- Validation et réconciliation des données

**1️⃣ Structure du projet MediCore**
MediCore/
│
├── 📄 README.md                                    # Documentation principale du projet
├── 📄 ARCHITECTURE.md                              # Architecture détaillée
├── 📄 SETUP.md                                     # Guide d'installation
├── 📄 .gitignore                                   # Fichiers à ignorer dans Git
├── 📄 requirements.txt                             # Dépendances Python
├── 📄 pyproject.toml                               # Configuration Python (moderne)
│
├── 📁 config/
│   ├── 📄 sources.yaml                             # Configuration connexion sources MySQL
│   ├── 📄 snowflake.yaml                           # Configuration connexion Snowflake
│   ├── 📄 pii_masking.yaml                         # Règles de masquage PII
│   ├── 📄 dbt_config.yaml                          # Configuration dbt
│   └── 📊 CoreModel.xlsx                           # Mapping sources (Excel)
│
├── 📁 pipelines/
│   ├── 📄 __init__.py
│   ├── 📄 cdc_ingestion.py                         # Capteur CDC MySQL et masquage
│   ├── 📄 snowflake_loader.py                      # Chargement Snowflake
│   ├── 📄 reconciliation.py                        # Réconciliation données
│   └── 📁 utils/
│       ├── 📄 __init__.py
│       ├── 📄 mysql_connector.py                   # Connexion MySQL
│       ├── 📄 snowflake_connector.py               # Connexion Snowflake
│       ├── 📄 pii_processor.py                     # Masquage PII
│       ├── 📄 audit_logger.py                      # Audit trail
│       ├── 📄 data_validator.py                    # Validation données
│       └── 📄 file_manager.py                      # Gestion fichiers
│
├── 📁 dbt/
│   ├── 📄 dbt_project.yml                          # Configuration dbt
│   ├── 📄 profiles.yml                             # Profiles Snowflake
│   ├── 📄 packages.yml                             # Packages dbt
│   ├── 📄 selectors.yml                            # Sélecteurs dbt
│   │
│   ├── 📁 models/
│   │   ├── 📁 raw/                                 # Couche RAW (données brutes)
│   │   │   ├── 📄 _raw.yml
│   │   │   ├── 📄 raw_pharmacie.sql
│   │   │   └── 📄 raw_produits.sql
│   │   │
│   │   ├── 📁 staging/                             # Couche STAGING (nettoyage)
│   │   │   ├── 📄 _staging.yml
│   │   │   ├── 📄 stg_pharmacie.sql
│   │   │   └── 📄 stg_produits.sql
│   │   │
│   │   └── 📁 marts/                               # Couche MARTS (sémantique)
│   │       ├── 📄 _marts.yml
│   │       ├── 📄 dim_pharmacie.sql
│   │       ├── 📄 dim_produits.sql
│   │       └── 📄 fact_vente.sql
│   │
│   ├── 📁 tests/
│   │   ├── 📄 assert_pharmacie_not_null.sql
│   │   ├── 📄 assert_unique_pha_id.sql
│   │   └── 📄 assert_row_count_increase.sql
│   │
│   ├── 📁 seeds/
│   │   └── 📄 mapping_sources.yml                  # Seeds de mapping
│   │
│   ├── 📁 macros/
│   │   ├── 📄 generate_schema_name.sql
│   │   └── 📄 get_masking_rule.sql
│   │
│   └── 📁 analysis/
│       └── 📄 data_lineage.sql
│
├── 📁 audit/
│   ├── 📁 manifests/
│   │   ├── 📄 2026-01-13_manifest.json             # Manifest d'exécution
│   │   └── 📄 manifest_schema.json                 # Schéma du manifest
│   │
│   ├── 📁 logs/
│   │   ├── 📄 2026-01-13.log
│   │   └── 📄 reconciliation_2026-01-13.log
│   │
│   ├── 📁 checksums/
│   │   └── 📄 2026-01-13_checksums.json            # Checksums de réconciliation
│   │
│   └── 📁 lineage/
│       ├── 📄 data_lineage_graph.json              # Graph de lineage
│       └── 📄 lineage_manifest.json                # Manifest lineage
│
├── 📁 orchestration/
│   ├── 📄 airflow_dag.py                           # DAG Airflow (optionnel)
│   ├── 📄 dbt_cloud_job.yaml                       # Job dbt Cloud (optionnel)
│   └── 📄 scheduler.sh                             # Script de scheduling
│
├── 📁 tests/
│   ├── 📄 __init__.py
│   ├── 📄 test_cdc_ingestion.py                    # Tests unitaires CDC
│   ├── 📄 test_snowflake_loader.py                 # Tests chargement
│   ├── 📄 test_pii_processor.py                    # Tests masquage
│   └── 📄 test_reconciliation.py                   # Tests réconciliation
│
├── 📁 docs/
│   ├── 📄 ARCHITECTURE.md                          # Documentation architecture
│   ├── 📄 DATA_LINEAGE.md                          # Documentation lineage
│   ├── 📄 PII_MASKING.md                           # Règles masquage
│   ├── 📄 OPERATIONS.md                            # Guide opérationnel
│   ├── 📄 TROUBLESHOOTING.md                       # Guide dépannage
│   └── 📁 images/
│       ├── 📊 architecture_diagram.png
│       ├── 📊 data_flow.png
│       └── 📊 lineage_example.png
│
└── 📁 scripts/
    ├── 📄 setup_project.sh                         # Script d'initialisation
    ├── 📄 install_dependencies.sh                  # Installation dépendances
    ├── 📄 run_full_pipeline.sh                     # Exécution pipeline complète
    ├── 📄 run_cdc_only.sh                          # CDC uniquement
    └── 📄 run_dbt_only.sh                          # dbt uniquement

## Structure
- **pipelines/** : Scripts Python (CDC, chargement, réconciliation)
- **dbt/** : Modèles de transformation (raw, staging, marts)
- **config/** : Configuration sources, masquage, connexions
- **audit/** : Logs, manifests, lineage
- **tests/** : Tests unitaires et intégration

## Installation rapide
```bash
git clone <repo>
cd MediCore
bash scripts/setup_project.sh
python -m pip install -r requirements.txt
```

<u>Exécution</u>
# Pipeline complet
bash scripts/run_full_pipeline.sh

# CDC seul
bash scripts/run_cdc_only.sh


**1️⃣ Architecture d'extraction industrialisée**
Approche hybride orientée ELT :
MySQL (Winstat) 
    ↓ [CDC via Debezium/MySQL binlog]
    ↓
Python (Extraction + Masquage)
    ↓
Snowflake (Staging) - RAW layer
    ↓ [dbt]
    ↓
Snowflake (Transformations) - Refined layer


**Composants clés :**
Phase 1 : CAPTURE (Python + MySQL CDC)
✅ MySQL Binlog → Python CDC Reader
✅ Détecte INSERTS/UPDATES/DELETES
✅ Applique masquage de données sensibles
✅ Crée fichiers JSON/Parquet versionnés
✅ Génère manifeste d'audit (timestamp, user, checksum)

Phase 2 : LOAD (Python → Snowflake)
✅ Charge données brutes dans layer RAW
✅ Staging tables avec surrogate keys
✅ Enregistre lineage (source, timestamp, volume)
✅ Versioning du mapping (CoreModel.xlsx)

Phase 3 : TRANSFORM (dbt → Snowflake)
✅ Transformations dans Snowflake (puissance calcul)
✅ Data quality checks
✅ Agrégations, joins, nettoyage
✅ Génération modèle sémantique

**2️⃣ CDC vs Batch quotidien.**
-----------------------------------------------------------------
| Aspect              | CDC seul    | Batch seul | CDC + Batch  |
| ------------------- | ----------- | ---------- | -------------|
| Temps réel          | ✅          | ❌        | ✅ (daily)   |
| Charges initiales   | ❌          | ✅        | ✅           |
| Changements rapides | ✅          | ❌        | ✅           |
| Réconciliation      | ❌ (risques)| ✅        | ✅           |
| Coût                | 🔴 Élevé    | 🟢 Bas    | 🟡 Équilibré |
-----------------------------------------------------------------

<u>Stratégie recommandée :</u>

Jour 1 : Batch full-load (snapshot initial)

Jour 2+ : CDC incremental (INSERTS/UPDATES/DELETES)

Chaque nuit : Batch de réconciliation (full-load sur tables critiques)

Cela garantit :

📊 Intégrité des données

⚡ Performance optimale

🔄 Récupération en cas d'erreur

**3️⃣ dbt + Python vs Approche hybride**
---------------------------------------------------------------------------------
┌────────────────┐┌──────────────────────┐┌───────────────────────────────────────────┐
┌────────────────┐────────────────────────┌───────────────────────────────────────────┐
│ Critère        │  dbt + Python          │ Approche hybride (Python + SQL + dbt)     │
│────────────────│────────────────────────│───────────────────────────────────────────│
│ Extraction     │  Python (direct)       │ Python (CDC, masquage)                    │
│ Chargement     │  Python (raw)          │ Python (raw)                              │
│ Transformation │  dbt (SQL)             │ dbt (SQL)                                 │
│ Masquage/PII   │  ❌ Difficile          │ ✅ En Python (avant load)                │
│ Audit trail    │  ⚠️ Limité             │ ✅ Complet (JSON manifest)               │
│ Scaling        │  🔴 Python CPU limité  │ 🟢 Snowflake compute                     │
│ Gouvernance    │  ⚠️ Moyen              │ ✅ Excellent                             │
└────────────────┘────────────────────────└───────────────────────────────────────────┘

Choix : Approche hybride, Python pour extraction/masquage/audit, dbt pour transformations massives

**4️⃣ ELT vs ETL**
ETL (Ancien modèle)           ELT (Moderne - cas MediCore)
┌─────────────────┐             ┌──────────────────────┐
│ Extraction      │             │ Extraction (CDC)     │
│ Transformation  │─ Python     │ Load RAW             │
│ Load            │ (limité)    │ Transform (Snowflake)│
└─────────────────┘             └──────────────────────┘
    Lent                          Rapide (high volume)
    Complexe                      Scalable
    Erreurs nombreuses            Audit trail

<u>Avantages ELT pour vos 18 Go :</u>

⚡ Snowflake peut traiter en parallèle

💾 Pas de limitations de RAM Python

🔄 Récalculs faciles (rejouer la transformation)

📈 Séparation responsabilités (extraction ≠ transformation)
