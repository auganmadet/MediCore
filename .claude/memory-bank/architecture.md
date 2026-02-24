# Architecture — MediCore ELT Pipeline

## Vue d'ensemble

Pipeline ELT industrialise pour l'ingestion et la transformation de donnees pharmacie depuis MySQL RDS vers Snowflake, via Debezium/Kafka pour le CDC et dbt pour les transformations.

## Flux de donnees

```
MySQL RDS (winstat)
    |
    +-- binlog stream --> Debezium --> Kafka (4 topics CDC)
    |                                    |
    |                                    v
    |                              daily_cdc_batch.py
    |                              (micro-batch 500 events)
    |                                    |
    +-- SELECT (1x/jour @ 03h) --> bulk_load.py
    |                              (Parquet chunks -> PUT @stage)
    |                                    |
    +------------------------------------+
                                         |
                                         v
                              Snowflake RAW (18 tables)
                                         |
                                         | dbt run --select tag:staging
                                         v
                              Snowflake STAGING (18 vues/incr.)
                              - Dedup CDC (ROW_NUMBER)
                              - Filtre deletes
                              - PII masking (MD5)
                                         |
                                         | dbt run --select tag:marts
                                         v
                              Snowflake MARTS (tables)
                              - 3 dimensions (surrogate keys)
                              - 8 faits (aggregations)
                              - KPIs metier
```

## Services Docker (6)

| Service | Image | Role |
|---------|-------|------|
| `medicore_elt_batch` | Custom (Dockerfile) | Pipeline Python + dbt |
| `mysql_cdc` | MySQL 8 | Source CDC locale (dev) |
| `kafka` | Confluent 7.5.0 | Message broker |
| `zookeeper` | Confluent 7.7.0 | Coordination Kafka |
| `connect` | Debezium 2.7.3 | CDC MySQL -> Kafka |
| `kafdrop` | obsidiandynamics | UI monitoring Kafka |

## Modules et responsabilites

| Module | Responsabilite |
|--------|----------------|
| `pipelines/daily_cdc_batch.py` | Consumer Kafka, micro-batch INSERT RAW |
| `pipelines/bulk_load.py` | MySQL SELECT, chunking Parquet, COPY INTO RAW |
| `pipelines/diagnose_recover.py` | Diagnostic, recovery, verification integrite |
| `dbt/models/staging/stg_*.sql` | Dedup CDC + PII masking + typage |
| `dbt/models/marts/dim_*.sql` | Dimensions avec surrogate keys |
| `dbt/models/marts/fact_*.sql` | Faits avec aggregations |
| `dbt/models/marts/mart_kpi_*.sql` | KPIs metier calcules |
| `dbt/macros/pii_masking.sql` | Macro MD5 pour colonnes PII |
| `scripts/batch_loop.sh` | Orchestration boucle (CDC -> STG -> MARTS -> tests) |
| `scripts/setup.sh` | Premier lancement (DDL + Docker + Debezium) |
| `scripts/entrypoint.sh` | Demarrage conteneur (attente services + deps) |
| `scripts/healthcheck.py` | Health check Docker (connectivite Snowflake) |

## Boucle d'orchestration (batch_loop.sh)

1. Bulk load reference (1x/jour @ 03h00) : `bulk_load.py --ref-only --truncate`
2. Consumer CDC : `daily_cdc_batch.py` (Kafka -> Snowflake RAW)
3. dbt staging : `dbt run --select tag:staging`
4. dbt marts : `dbt run --select tag:marts`
5. dbt tests : `dbt test --select stg_*`
6. Source freshness : `dbt source freshness`
7. Alertes Teams : webhook si echec/recovery

**Intervalle** : 5 min (dev) / 30 min (prod)

## Patterns de conception

- **Medallion Architecture** : RAW -> STAGING -> MARTS (3 couches)
- **CDC + Bulk dual path** : temps reel (4 tables) + batch (14 tables)
- **Incremental merge** : pas de retraitement complet, merge sur PK
- **DLQ (Dead Letter Queue)** : events CDC malformes isoles
- **Micro-batch** : 500 events ou timeout 30s avant flush Snowflake
- **Star schema** : dimensions (surrogate keys) + faits (FK + mesures)
- **PII masking** : MD5 en staging, jamais en clair apres RAW
- **Monitoring adaptatif** : alerte apres 3 echecs, notification recovery

## Points d'architecture cles

- **RAW = source de verite brute** : aucune transformation, metadonnees CDC preservees
- **Staging = nettoyage** : dedup, filtre deletes, PII, typage
- **Marts = valeur metier** : star schema, KPIs, pret pour BI
- **Pas d'orchestrateur externe** : boucle bash simple et robuste
- **Docker-first** : tous les services conteneurises avec health checks
