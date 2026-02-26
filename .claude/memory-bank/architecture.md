# Architecture — MediCore ELT Pipeline

## Vue d'ensemble

Pipeline ELT industrialisé pour l'ingestion et la transformation de données pharmacie depuis MySQL RDS vers Snowflake, via Debezium/Kafka pour le CDC et dbt pour les transformations.

## Flux de données

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
                              - Dédup CDC (ROW_NUMBER)
                              - Filtre deletes
                              - PII masking (MD5)
                                         |
                                         | dbt run --select tag:marts
                                         v
                               Snowflake MARTS (tables)
                               - 3 dimensions (surrogate keys + lignes orphelines -1)
                               - 8 faits (LEFT JOIN + coalesce orphelins)
                               - KPIs métier
                                          |
                                          | dbt snapshot
                                          v
                               Snowflake SNAPSHOTS (SCD2)
                               - snap_pharmacie, snap_produit, snap_fournisseur
                                          |
                                          | dbt run --select tag:audit
                                          v
                               Snowflake AUDIT (vues)
                               - audit_run_summary, audit_dbt_summary, audit_latest_runs
```

## Services Docker (6)

  ┌──────────────────────┬─────────────────────┬─────────────────────────┐
  │       Service        │        Image        │          Rôle           │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `medicore_elt_batch` │ Custom (Dockerfile) │ Pipeline Python + dbt   │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `mysql_cdc`          │ MySQL 8             │ Source CDC locale (dev) │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `kafka`              │ Confluent 7.5.0     │ Message broker          │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `zookeeper`          │ Confluent 7.7.0     │ Coordination Kafka      │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `connect`            │ Debezium 2.7.3      │ CDC MySQL -> Kafka      │
  ├──────────────────────┼─────────────────────┼─────────────────────────┤
  │ `kafdrop`            │ obsidiandynamics    │ UI monitoring Kafka     │
  └──────────────────────┴─────────────────────┴─────────────────────────┘

## Modules et responsabilités

  ┌───────────────────────────────────┬─────────────────────────────────────────────────────┐
  │              Module               │                   Responsabilité                    │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `pipelines/daily_cdc_batch.py`    │ Consumer Kafka, micro-batch INSERT RAW              │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `pipelines/bulk_load.py`          │ MySQL SELECT, chunking Parquet, COPY INTO RAW       │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `pipelines/diagnose_recover.py`   │ Diagnostic, recovery, vérification intégrité        │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/models/staging/stg_*.sql`    │ Dédup CDC + PII masking + typage                    │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/models/marts/dim_*.sql`      │ Dimensions avec surrogate keys                      │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/models/marts/fact_*.sql`     │ Faits avec agrégations                              │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/models/marts/mart_kpi_*.sql` │ KPIs métier calculés                                │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/macros/pii_masking.sql`      │ Macro pii_mask() pour colonnes PII (MD5 tronqué)    │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/macros/guard_full_refresh.sql` │ Protection full-refresh sur modèles high_volume   │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/snapshots/snap_*.sql`        │ 3 snapshots SCD2 (pharmacie, produit, fournisseur)  │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `dbt/models/audit/audit_*.sql`    │ 3 modèles audit (run_summary, dbt_summary, latest)  │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `scripts/batch_loop.sh`           │ Orchestration boucle (CDC -> STG -> MARTS -> tests) │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `scripts/setup.sh`                │ Premier lancement (DDL + Docker + Debezium)         │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `scripts/entrypoint.sh`           │ Démarrage conteneur (attente services + deps)       │
  ├───────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ `scripts/healthcheck.py`          │ Health check Docker (connectivité Snowflake)        │
  └───────────────────────────────────┴─────────────────────────────────────────────────────┘

## Boucle d'orchestration (batch_loop.sh)

1. Bulk load référence (1x/jour @ 03h00) : `bulk_load.py --ref-only --truncate`
2. Consumer CDC : `daily_cdc_batch.py` (Kafka -> Snowflake RAW)
3. dbt staging : `dbt run --select tag:staging`
4. dbt marts : `dbt run --select tag:marts`
5. dbt tests : `dbt test --select stg_*`
6. Source freshness : `dbt source freshness`
7. Alertes Teams : webhook si échec/recovery

**Intervalle** : 5 min (dev) / 30 min (prod)

## Patterns de conception

- **Medallion Architecture** : RAW -> STAGING -> MARTS (3 couches)
- **CDC + Bulk dual path** : temps réel (4 tables) + batch (14 tables)
- **Incremental merge** : pas de retraitement complet, merge sur PK
- **DLQ (Dead Letter Queue)** : events CDC malformés isolés
- **Micro-batch** : 500 events ou timeout 30s avant flush Snowflake
- **Star schema** : dimensions (surrogate keys + lignes orphelines -1/INCONNU) + faits (LEFT JOIN + coalesce FK)
- **PII masking** : macro `pii_mask()` en staging (MD5 tronqué avec prefix), jamais en clair après RAW
- **Monitoring adaptatif** : alerte après 3 échecs, notification recovery
- **Guard full-refresh** : macro bloquant le `--full-refresh` sur modèles `high_volume` (bypass explicite requis)
- **SCD Type 2** : 3 snapshots dbt (pharmacie, produit, fournisseur) avec strategy `check`
- **Audit trail** : 3 modèles audit dbt traçant les runs et métriques qualité
- **Cluster keys** : `CLUSTER BY (CDC_TIMESTAMP)` sur tables RAW high-volume (commandes, daybyday, orders)

## Points d'architecture clés

- **RAW = source de vérité brute** : aucune transformation, métadonnées CDC préservées
- **Staging = nettoyage** : dédup, filtre deletes, PII, typage
- **Marts = valeur métier** : star schema, KPIs, prêt pour BI
- **Pas d'orchestrateur externe** : boucle bash simple et robuste
- **Docker-first** : tous les services conteneurisés avec health checks
