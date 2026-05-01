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
    +-- SELECT (1x/jour @ 23h FR) --> bulk_load.py
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

### Surveillance à 4 niveaux (depuis 2026-04-23)

- **N1 pre-night (20h30 FR)** : `pre_night_healthcheck.py --fix` valide infra + config avant la nuit, auto-corrige ce qui peut l'être, crée `/tmp/pre_night_ok` ou alerte Teams.
- **N2a post CDC pré-reload (~21h35)** : vérifie flag + lag Kafka acceptable (warning non bloquant).
- **N2b post ref_reload (~23h16)** : vérifie 14 tables non vides + 0 `_BACKUP` résiduel. **Bloquant** : si KO, `REF_DONE_FLAG` non créé → dbt post-reload skippé.
- **N3 pipeline_maintenance (~23h47)** : audit final 4 phases (CDC, Bulk, dbt, Metabase) avec corrections sûres.

### Logique hebdomadaire ref_reload (L1+L5)

- **Dimanche** (DOW=0) : `SKIP` complet (pharmacies fermées).
- **Lundi** (DOW=1) : `FULL` reload classique (`--truncate`) pour réconciliation hebdomadaire (DELETEs captés).
- **Mardi→Samedi** (DOW=2..6) : `INCREMENTAL` 30 jours glissants (`--incremental-days 30`) sur 4 tables (MEDIPRIX_FACTURES, STOCKHISTORY, DAYBYDAY, MANQHISTORY) + TRUNCATE classique sur les 10 autres.

### Enchaînement nocturne typique (jour incremental)

1. 20h30 FR : pre-night healthcheck (30 s)
2. 21h30 FR : CDC pré-reload (quelques minutes) + post-check 2a
3. 22h00 FR : audit purge + backup Metabase
4. 23h00 FR : ref_reload (~53 min mesuré 25/04 en incremental ; clustering RAW_MEDIPRIX_FACTURES (PHA_ID, FAC_DATE) appliqué le 27/04, durée attendue 5-10 min sur MEDIPRIX, total ~16-22 min ; ~4h48 en full lundi)
5. 23h59 FR : post-check 2b + REF_DONE_FLAG (heures basées sur run du 25/04)
6. 00h00 FR : dbt post-reload (CDC flush + staging + marts + tests + freshness, ~39 min mesuré)
7. 00h39 FR : pipeline_maintenance `--fix-safe` (~11 min) + rapport Teams + dev auto-clone (~20 s)

### Consumer CDC (cycle court)

- `daily_cdc_batch.py` (Kafka → Snowflake RAW), intervalle **10 min (prod) / 2 min (dev)**.
- Circuit-breaker : arrêt du fallback row-by-row après 10 échecs consécutifs (`FALLBACK_MAX_CONSECUTIVE_FAILS`).
- Reconnexion auto sur session Snowflake expirée (codes 390114, 390116, 390111).
- Commit Kafka conditionnel au flush réussi (`if flush_ok: consumer.commit()`).
- DLQ sur connexion dédiée pour survivre à une session main morte.

### Alertes Teams

- Webhook si échec/recovery (seuil 3 échecs consécutifs).
- Rapport dbt après chaque phase staging/marts/tests.
- Alerte critique si pre-night KO (skip toute la nuit).
- Alerte warning si post-check 2a KO, critique si 2b KO.

## Patterns de conception

- **Medallion Architecture** : RAW -> STAGING -> MARTS (3 couches)
- **CDC + Bulk dual path** : temps réel (4 tables) + batch (14 tables)
- **Incremental merge côté ref_reload** (L1) : 4 grosses tables (MEDIPRIX_FACTURES, STOCKHISTORY, DAYBYDAY, MANQHISTORY) chargées sur fenêtre 30 jours glissants avec MERGE INTO sur PK, sauf full reload du lundi
- **Skip dimanche** (L5) : pas de ref_reload le dimanche (pharmacies fermées)
- **Incremental merge côté dbt staging** : `ROW_NUMBER() OVER (PARTITION BY PK ORDER BY cdc_timestamp DESC)` filtre `WHERE cdc_operation != 'D'`
- **DLQ (Dead Letter Queue)** : events CDC malformés isolés
- **Micro-batch** : 500 events ou timeout 30s avant flush Snowflake
- **Star schema** : dimensions (surrogate keys + lignes orphelines -1/INCONNU) + faits (LEFT JOIN + coalesce FK)
- **PII masking** : macro `pii_mask()` en staging (MD5 tronqué avec prefix), jamais en clair après RAW
- **Monitoring adaptatif** : alerte après 3 échecs, notification recovery
- **Guard full-refresh** : macro bloquant le `--full-refresh` sur modèles `high_volume` (bypass explicite requis)
- **SCD Type 2** : 3 snapshots dbt (pharmacie, produit, fournisseur) avec strategy `check`
- **Audit trail** : 3 modèles audit dbt traçant les runs et métriques qualité
- **Cluster keys** : `CLUSTER BY (CDC_TIMESTAMP)` sur tables RAW high-volume (commandes, daybyday, orders)

## CI/CD Pipeline (GitHub Actions)

```
Push / PR sur main
    |
    +-- Job 1 : Lint Python (flake8)
    +-- Job 2 : Valider syntaxe dbt (dbt deps + dbt parse)
    +-- Job 3 : Build Docker image
    +-- Job 4 : Lint Bash (ShellCheck)
    +-- Job 5 : Push Docker image → GHCR (ghcr.io/auganmadet/medicore:latest)
```

- **Fichier** : `.github/workflows/ci.yml`
- **Registry** : GitHub Container Registry (GHCR)
- **Déclenchement** : push sur `main`, pull requests

## Points d'architecture clés

- **RAW = source de vérité brute** : aucune transformation, métadonnées CDC préservées
- **Staging = nettoyage** : dédup, filtre deletes, PII, typage
- **Marts = valeur métier** : star schema, KPIs, prêt pour BI
- **Pas d'orchestrateur externe** : boucle bash simple et robuste
- **Docker-first** : tous les services conteneurisés avec health checks
