---
description: Architecture du pipeline ELT et patterns de conception. Appliquer lors de toute modification structurelle.
globs: "pipelines/**/*.py,dbt/**/*.sql"
---

- Pipeline : MySQL RDS -> Kafka CDC -> Snowflake RAW -> dbt STG -> dbt MARTS
- 3 couches : RAW (brut) -> STAGING (dédup + PII) -> MARTS (star schema)
- 4 tables CDC via Debezium/Kafka : COMMANDES, FACTURES, ORDERS, MODSTOCK
- 14 tables référence via bulk load : DAYBYDAY, EAN13, FOURNISSEURS, etc.
- `daily_cdc_batch.py` : consumer Kafka micro-batch (500 events)
- `bulk_load.py` : MySQL -> Parquet -> PUT @stage -> COPY INTO
- `batch_loop.sh` : orchestration principale (boucle 5-30 min)
- dbt staging : dédup CDC (`ROW_NUMBER`) + filtre deletes + PII masking
- dbt marts : dimensions (surrogate keys) + faits (agrégations) + KPIs
- Incremental merge strategy sur les modèles haute volumétrie
- Monitoring Teams webhook sur échecs/recovery
- Source freshness : CDC 12h/24h, référence 36h/48h
- DLQ (Dead Letter Queue) pour events CDC non traitables
- Pas de logique métier dans les pipelines Python (RAW = brut)
- Transformations métier exclusivement dans dbt (STG/MARTS)
