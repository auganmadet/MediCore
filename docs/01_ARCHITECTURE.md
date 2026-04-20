# Architecture MediCore

## Table des matières

1. [Vue d'ensemble : Architecture data](#vue-densemble--architecture-data-slide-7---docsmedicore_presentationpptx)
2. [Flux de données global](#flux-de-données-global)
3. [Layers Snowflake](#layers-snowflake)
   - [RAW Layer](#raw-layer)
   - [STAGING Layer](#staging-layer)
   - [MARTS Layer](#marts-layer)
   - [Pourquoi Kafka plutôt qu'une connexion directe ?](#pourquoi-kafka-plutot-quune-connexion-directe-)
   - [Composants Snowflake DWH](#composants-snowflake-dwh)
   - [Couche Exposition](#couche-exposition)
4. [Services Docker](#services-docker)
5. [Monitoring](#monitoring)
6. [Fichiers clés](#fichiers-clés)

---

## Vue d'ensemble : Architecture data (slide 7 - docs\MediCore_Presentation.pptx)

```
┌──────────────┐    ┌────────────────────────┐    ┌──────────────────────────────────────────────────────┐    ┌──────────────────────┐
│   SOURCES    │    │       INGESTION        │    │                  SNOWFLAKE DWH                       │    │     EXPOSITION       │
│              │    │                        │    │                                                      │    │                      │
│ ┌──────────┐ │    │ ┌──────────────────┐   │    │ ┌───────┐  ┌────────────────────────────────────┐    │    │ ┌──────────────────┐ │
│ │ MySQL RDS│ │    │ │ Debezium 2.7     │   │    │ │       │  │     Transformation dbt             │    │    │ │ Power BI         │ │
│ │ winstat  │─┼───>│ │ CDC binlog       │   │    │ │       │  │                                    │    │    │ │ dashboards       │ │
│ └──────────┘ │    │ └───────┬──────────┘   │    │ │       │  │ ┌─────────┐    ┌───────────────┐   │    │    │ └──────────────────┘ │
│              │    │ ┌───────▼──────────┐   │    │ │  RAW  │  │ │ STAGING │    │    MARTS      │   │    │    │ ┌──────────────────┐ │
│ ┌──────────┐ │    │ │ Kafka            │───┼───>│ │       ┼─>│ │ 18 mod. ┼───>│  3 DIM        │   ┼────┼───>│ │ Tableau          │ │
│ │ 4 tables │ │    │ │ 4 topics         │   │    │ │ 18    │  │ │ dedup   │    │  8 FAITS      │   │    │    │ │ visualisation    │ │
│ │   CDC    │─┼───>│ └───────┬──────────┘   │    │ │tables │  │ │ + PII   │    │  21 KPIs      │   │    │    │ └──────────────────┘ │
│ └──────────┘ │    │ ┌───────▼──────────┐   │    │ │brutes │  │ └─────────┘    └───────────────┘   │    │    │ ┌──────────────────┐ │
│              │    │ │ Python CDC       │   │    │ │       │  │                                    │    │    │ │ Metabase         │ │
│ ┌──────────┐ │    │ │ micro-batch 500  │───┼───>│ │       │  └────────────────────────────────────┘    │    │ │ self-service BI  │ │
│ │14 tables │ │    │ └──────────────────┘   │    │ │       │                                            │    │ └──────────────────┘ │
│ │   REF    │─┼───>│ ┌──────────────────┐   │    │ │       │  ┌────────────────────────────────────┐    │    │ ┌──────────────────┐ │
│ └──────────┘ │    │ │ Python Bulk      │───┼───>│ │       │  │            dbt                     │    │    │ │ API / Exports    │ │
│              │    │ │ Parquet+COPY INTO│   │    │ └───────┘  │ ┌───────────┐ ┌──────────────────┐ │    │    │ │ integrations     │ │
│              │    │ └──────────────────┘   │    │            │ │ AUDIT     │ │ SNAPSHOTS        │ │    │    │ └──────────────────┘ │
│              │    │                        │    │            │ │ lineage + │ │ SCD2 dimensions  │ │    │    │                      │
│              │    │                        │    │            │ │ runs      │ │                  │ │    │    │                      │
│              │    │                        │    │            │ └───────────┘ └──────────────────┘ │    │    │                      │
│              │    │                        │    │            └────────────────────────────────────┘    │    │                      │
└──────────────┘    └────────────────────────┘    └──────────────────────────────────────────────────────┘    └──────────────────────┘


```

[↑ Retour au sommaire](#table-des-matières)

## Flux de données global

**Prérequis MySQL binlog** (vérifiés par `scripts/setup.sh`) :

  Sur AWS RDS, les variables MySQL ne se modifient pas avec SET GLOBAL (pas d'accès SUPER) — il faut passer par un Parameter Group dans la console AWS RDS :

  1. AWS Console → RDS → Parameter Groups
  2. Modifier (ou créer) le parameter group associé à l'instance RDS
  3. Changer les 3 variables
  4. Redémarrer l'instance RDS pour appliquer

  ┌────────────────────────────────────┬────────┬──────────────────────────────────────────┐
  │ Variable MySQL                     │ Requis │ Pourquoi                                 │
  ├────────────────────────────────────┼────────┼──────────────────────────────────────────┤
  │ binlog_format                      │ ROW    │ Debezium capture les changements ligne   │
  │                                    │        │ par ligne (pas les statements SQL)       │
  ├────────────────────────────────────┼────────┼──────────────────────────────────────────┤
  │ binlog_row_image                   │ FULL   │ Chaque event contient toutes les colonnes│
  │                                    │        │ (before + after), pas seulement les      │
  │                                    │        │ colonnes modifiées                       │
  ├────────────────────────────────────┼────────┼──────────────────────────────────────────┤
  │ log_bin_trust_function_creators    │ ON     │ Autorise la réplication des fonctions    │
  │                                    │        │ stockées via le binlog                   │
  └────────────────────────────────────┴────────┴──────────────────────────────────────────┘

```
┌───────────┐   binlog    ┌──────────┐         ┌─────────┐
│ MySQL RDS │───────────▶│ Debezium │────────▶│  Kafka  │
│ (winstat) │             │ (Connect)│         │ 4 topics│
└─────┬─────┘             └──────────┘         └────┬────┘
      │                                             │
      │  SELECT * (14 réf)                          │ consume (4 CDC)
      │                                             │
      ▼                                             ▼
┌─────────────┐                           ┌──────────────────┐
│ bulk_load.py│                           │daily_cdc_batch.py│
│ Parquet+PUT │                           │ Kafka→INSERT     │
└──────┬──────┘                           └────────┬─────────┘
       │                                           │
       └──────────────┬────────────────────────────┘
                      │ COPY INTO / INSERT
                      ▼
              ┌───────────────┐
              │ Snowflake RAW │  18 tables
              └───────┬───────┘
                      │ dbt run tag:staging
                      ▼
              ┌───────────────┐
              │ Snowflake STG │  18 modèles (dédup CDC + PII masking)
              └───────┬───────┘
                      │ dbt run tag:marts
                      ▼
              ┌───────────────┐
              │Snowflake MARTS│  3 dims + 8 facts
              └───────────────┘

```

[↑ Retour au sommaire](#table-des-matières)

## Layers Snowflake

### RAW Layer
- Données brutes depuis CDC (Kafka) et bulk load (MySQL SELECT)
- Colonnes metadata : CDC_OPERATION, CDC_TIMESTAMP, CDC_LSN
- CLUSTER BY (CDC_TIMESTAMP) sur les 4 tables CDC
- Aucune transformation

### STAGING Layer
- Déduplication CDC (ROW_NUMBER OVER PARTITION BY PK ORDER BY CDC_TIMESTAMP DESC)
- Filtre CDC_OPERATION != 'D' (exclut les deletes)
- PII masking (md5 sur colonnes sensibles : noms, adresses, téléphones)
- Renommage et cast colonnes

### MARTS Layer
- Star schema : dimensions + faits
- Dimensions avec membre par défaut INCONNU (SK = md5('-1' || '-' || '-1'))
- LEFT JOIN facts → dims avec COALESCE pour orphan rows
- Matérialisées en tables


### Pourquoi Kafka plutot qu'une connexion directe ?

1. **Decouplage** : si Snowflake est indisponible, Kafka conserve les messages
2. **Rejouabilite** : possibilite de rejouer un offset en cas d'erreur
3. **Scalabilite** : possibilite de mettre plusieurs consumers en parallele

### Composants Snowflake DWH

- **RAW** (BRONZE) : donnees brutes sans transformation — c'est le principe ELT
- **STAGING** (SILVER) : deduplication CDC + masquage PII (MD5)
- **MARTS** (GOLD) : star schema — 3 DIM, 8 FAITS, 21 KPIs
- **AUDIT** : tables PIPELINE_RUNS, STEP_RUNS et DBT_MODEL_RUNS — tracabilite a chaque execution. Quand un KPI semble faux, on remonte au RUN_ID pour identifier si c'est un probleme d'ingestion ou de transformation
- **SNAPSHOTS** : SCD2 (Slowly Changing Dimension Type 2). Quand une dimension change (pharmacie qui change de nom, produit qui change de fournisseur), l'ancienne valeur est conservee avec une date de fin. Les ventes de fevrier s'affichent avec l'ancien nom, celles de mars avec le nouveau

### Couche Exposition

  ┌──────────────────┬──────────────────────────────────────────────────────────────┐
  │ Outil            │ Description                                                  │
  ├──────────────────┼──────────────────────────────────────────────────────────────┤
  │ Power BI         │ Integration Microsoft native, DAX puissant.                  │
  │                  │ Inconvenient : verrouille dans l'ecosysteme Microsoft.       │
  ├──────────────────┼──────────────────────────────────────────────────────────────┤
  │ Tableau          │ Reference en data visualisation, connexion native Snowflake. │
  │                  │ Inconvenient : cout eleve (~70$/utilisateur/mois).           │
  ├──────────────────┼──────────────────────────────────────────────────────────────┤
  │ Metabase         │ Open-source, self-hosted, SQL natif, gratuit.                │
  │                  │ Deploye dans le stack Docker (`localhost:3000`).             │
  ├──────────────────┼──────────────────────────────────────────────────────────────┤
  │ API / Exports    │ Integration KPIs dans ERP, CRM, applications metier.         │
  │                  │ Exports CSV/Excel pour partenaires (labos, groupements).     │
  └──────────────────┴──────────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

## Services Docker

```
  ┌────────────────────┬───────────────────────────────────┬───────────────────────────────────┬──────────────────────────────┐
  │ Service            │ Image                             │ Rôle                              │ Healthcheck                  │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ medicore_elt_batch │ Build local (Dockerfile)          │ Pipeline principal (batch_loop.sh)│ healthcheck.py (Snowflake)   │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ mysql_cdc          │ debezium/example-mysql:2.7.3      │ MySQL démo (Winstat local)        │ mysqladmin ping              │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ zookeeper          │ confluentinc/cp-zookeeper:7.7.0   │ Coordination Kafka                │ echo ruok                    │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ kafka              │ confluentinc/cp-kafka:7.5.0       │ Broker Kafka (4 topics CDC)       │ kafka-broker-api-versions    │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ kafka_connect      │ debezium/connect:2.7.3            │ Connecteur Debezium MySQL         │ curl REST API                │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ kafdrop            │ obsidiandynamics/kafdrop          │ UI monitoring topics              │ -                            │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ metabase_db        │ postgres:16-alpine                │ Metadata Metabase (PostgreSQL)    │ pg_isready                   │
  ├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
  │ metabase           │ metabase/metabase:v0.58.7         │ BI dashboards (Snowflake MARTS)   │ -                            │
  └────────────────────┴───────────────────────────────────┴───────────────────────────────────┴──────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

## Monitoring

- **Teams webhook** : alertes échec (seuil consécutif) + recovery
- **Source freshness** : CDC 12h warn / 24h error, référence 36h warn / 48h error
- **dbt test** : not_null, unique, relationships, expression_is_true (severity warn)
- **Docker healthcheck** : depends_on condition: service_healthy
- **Lag Kafka** : alerte si lag > seuil N fois consécutives

[↑ Retour au sommaire](#table-des-matières)

## Fichiers clés

  ┌──────────────────────────────────┬────────────────────────────────────────────────────────────────┐
  │ Fichier                          │ Rôle                                                           │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ scripts/setup.sh                 │ Premier lancement (HOST : DDL + Docker + Debezium)             │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ scripts/entrypoint.sh            │ Démarrage container (wait deps + dbt deps + cleanup lock)      │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ scripts/batch_loop.sh            │ Boucle principale (CDC + dbt + tests + freshness + alertes)    │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ pipelines/daily_cdc_batch.py     │ Consumer Kafka Debezium → INSERT RAW (4 tables)                │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ pipelines/bulk_load.py           │ MySQL SELECT → Parquet → COPY INTO RAW (18 tables)             │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ dbt/models/sources.yml           │ 18 sources RAW + freshness config                              │
  ├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ scripts/DDL_TABLES.sql           │ 18 tables RAW + AUDIT schema + ANALYST grants                  │
  └──────────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

---

## Voir aussi

- [Workflow multi-environnement](02_workflow_multi_env.md) — flux DEV/TEST/PROD et CI/CD
- [Opérations](03_operations.md) — exploitation quotidienne et monitoring

[↑ Retour au sommaire](#table-des-matières)