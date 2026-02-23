# MediCore - Pipeline ELT Pharmacie

Pipeline ELT industrialise : MySQL RDS → Kafka CDC → Snowflake RAW → dbt (STG/MARTS).
18 tables (4 CDC + 14 reference), monitoring Teams webhook, source freshness.

## Architecture

Voir [Architecture detaillee](docs/ARCHITECTURE.md) pour les schemas complets (flux, services Docker, monitoring).

## Structure du projet

```
MediCore/
├── docker-compose.yml                  # 6 services (ELT, MySQL, Kafka, Zookeeper, Connect, Kafdrop)
├── Dockerfile                          # Image medicore_elt_batch
├── requirements.txt                    # Dependances Python
├── .env                                # Variables d'environnement (non versionne)
│
├── pipelines/
│   ├── daily_cdc_batch.py              # Consumer Kafka → INSERT RAW (4 tables CDC)
│   ├── bulk_load.py                    # MySQL SELECT → Parquet → COPY INTO RAW (18 tables)
│   └── utils/
│       └── pii_masking.py              # Masquage PII (utilise par dbt staging)
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml                    # dbt_utils
│   ├── models/
│   │   ├── sources.yml                 # 18 sources RAW + freshness (4 CDC + 14 ref)
│   │   ├── staging/
│   │   │   ├── _staging.yml            # Tests staging
│   │   │   └── stg_*.sql              # 18 modeles staging (dedup CDC + PII masking)
│   │   └── marts/
│   │       ├── _marts.yml              # Tests marts
│   │       ├── dim_*.sql              # 3 dimensions (produit, fournisseur, pharmacie)
│   │       └── fact_*.sql             # 8 faits (ventes, commandes, stock, ruptures...)
│   └── macros/
│       └── pii_masking.sql
│
├── scripts/
│   ├── setup.sh                        # Premier lancement (HOST : DDL + Docker + Debezium)
│   ├── entrypoint.sh                   # Demarrage container (wait deps + dbt deps + batch)
│   ├── batch_loop.sh                   # Boucle principale (CDC + dbt + tests + freshness + alertes)
│   ├── healthcheck.py                  # Docker HEALTHCHECK (connexion Snowflake)
│   ├── DDL_WH.sql                      # Warehouse, roles, grants Snowflake
│   └── DDL_TABLES.sql                  # 18 tables RAW + CLUSTER BY
│
└── docs/
    └── ARCHITECTURE.md
```

## Installation

```bash
# Prerequis : Docker, snowsql, jq
# 1. Configurer .env avec les credentials
# 2. Premier lancement :
bash scripts/setup.sh --with-snowflake-ddl
```

## Fonctionnement

Le conteneur `medicore_elt_batch` execute `batch_loop.sh` en boucle (5 min dev / 30 min prod) :

1. **Re-bulk reference** (1x/jour a 03h) : `bulk_load.py --ref-only --truncate` (14 tables)
2. **CDC** : `daily_cdc_batch.py` consomme les events Kafka (4 tables)
3. **dbt staging** : `dbt run --select tag:staging` (dedup + PII masking)
4. **dbt marts** : `dbt run --select tag:marts` (dims + facts)
5. **dbt test** : `dbt test --select stg_*` (not_null, unique, relationships)
6. **Source freshness** : `dbt source freshness` (detecte donnees stales)

## Monitoring

- **Teams webhook** : alertes echec/recovery sur chaque phase (seuil configurable)
- **Source freshness** : CDC warn 12h / error 24h, reference warn 36h / error 48h
- **Docker healthcheck** : tous les services avec healthcheck + depends_on condition
- **Resource limits** : mem_limit + cpus sur les 6 conteneurs
