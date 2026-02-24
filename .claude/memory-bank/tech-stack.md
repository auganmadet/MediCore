# Tech Stack — MediCore ELT Pipeline

## Langage principal

- **Python 3.11** — Pipelines d'ingestion
- **SQL (Snowflake)** — Transformations dbt
- **Bash** — Orchestration et scripts

## Dépendances Python runtime

  ┌──────────────────────────────────────┬─────────┬──────────────────────────────────────┐
  │               Package                │ Version │                Usage                 │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `snowflake-connector-python[pandas]` │ 3.12.4  │ Driver Snowflake + support pandas    │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `mysql-connector-python`             │ 8.4.0   │ Driver MySQL pour bulk load          │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `kafka-python`                       │ 2.0.2   │ Consumer Kafka pour CDC              │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `pandas`                             │ 2.1.4   │ Manipulation DataFrames (chunking)   │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `pyarrow`                            │ 14.0.1  │ Format Parquet pour staging fichiers │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `dbt-core`                           │ 1.8.0   │ Framework transformation SQL         │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `dbt-snowflake`                      │ 1.8.0   │ Adaptateur Snowflake pour dbt        │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `requests`                           │ 2.31.0  │ Webhook Teams pour monitoring        │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `pyyaml`                             │ 6.0.1   │ Parsing configuration YAML           │
  ├──────────────────────────────────────┼─────────┼──────────────────────────────────────┤
  │ `python-dotenv`                      │ 1.0.0   │ Chargement variables .env            │
  └──────────────────────────────────────┴─────────┴──────────────────────────────────────┘

## Infrastructure

  ┌──────────────┬──────────────────┬───────────┬────────────────────────────────┐
  │  Composant   │   Technologie    │  Version  │              Rôle              │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ Source       │ MySQL            │ 8.x (RDS) │ Base source winstat            │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ CDC          │ Debezium         │ 2.7.3     │ Capture changements binlog     │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ Broker       │ Kafka            │ 7.5.0     │ Transport events CDC           │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ Coordination │ Zookeeper        │ 7.7.0     │ Coordination Kafka             │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ DWH          │ Snowflake        │ —         │ Data warehouse (RAW/STG/MARTS) │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ Conteneurs   │ Docker + Compose │ —         │ Orchestration services         │
  ├──────────────┼──────────────────┼───────────┼────────────────────────────────┤
  │ Monitoring   │ Kafdrop          │ latest    │ UI Kafka topics                │
  └──────────────┴──────────────────┴───────────┴────────────────────────────────┘

## Patterns techniques

- **Medallion Architecture** — RAW -> STG -> MARTS (3 couches)
- **CDC dual path** — Kafka temps réel + bulk quotidien
- **Micro-batch** — 500 events ou timeout 30s
- **Incremental merge** — dbt merge sur clé primaire composite
- **Star schema** — Dimensions (surrogate keys) + Faits (FK + mesures)
- **PII masking** — MD5 dans macros dbt staging
- **DLQ** — Dead Letter Queue pour events malformés
- **Health checks** — Docker + Snowflake connectivité

## Formats

- **Ingestion bulk** : MySQL -> pandas DataFrame -> Parquet -> Snowflake stage
- **Ingestion CDC** : Kafka JSON -> parse Debezium -> INSERT SQL
- **Transformation** : dbt SQL/Jinja2 (CTEs, incremental, macros)
- **Monitoring** : Adaptive Card JSON -> Teams webhook
- **Configuration** : `.env` + `profiles.yml` + `dbt_project.yml`

## Infrastructure de développement

- **Conteneurs** : Docker Compose (6 services)
- **Gestionnaire de paquets** : pip (requirements.txt)
- **VCS** : Git
- **Transformations** : dbt 1.8.0
- **Tests** : dbt tests (not_null, unique, relationships, freshness)
- **CI/CD** : Non configuré (orchestration via batch_loop.sh)
