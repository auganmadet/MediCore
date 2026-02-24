---
description: Architecture du pipeline ELT et patterns de conception. Appliquer lors de toute modification structurelle.
globs: "pipelines/**/*.py,dbt/**/*.sql"
---

- Pipeline : MySQL RDS -> Kafka CDC -> Snowflake RAW -> dbt STG -> dbt MARTS
- 3 couches : RAW (brut) -> STAGING (dedup + PII) -> MARTS (star schema)
- 4 tables CDC via Debezium/Kafka : COMMANDES, FACTURES, ORDERS, MODSTOCK
- 14 tables reference via bulk load : DAYBYDAY, EAN13, FOURNISSEURS, etc.
- `daily_cdc_batch.py` : consumer Kafka micro-batch (500 events)
- `bulk_load.py` : MySQL -> Parquet -> PUT @stage -> COPY INTO
- `batch_loop.sh` : orchestration principale (boucle 5-30 min)
- dbt staging : dedup CDC (`ROW_NUMBER`) + filtre deletes + PII masking
- dbt marts : dimensions (surrogate keys) + faits (aggregations) + KPIs
- Incremental merge strategy sur les modeles haute volumetrie
- Monitoring Teams webhook sur echecs/recovery
- Source freshness : CDC 12h/24h, reference 36h/48h
- DLQ (Dead Letter Queue) pour events CDC non traitables
- Pas de logique metier dans les pipelines Python (RAW = brut)
- Transformations metier exclusivement dans dbt (STG/MARTS)
