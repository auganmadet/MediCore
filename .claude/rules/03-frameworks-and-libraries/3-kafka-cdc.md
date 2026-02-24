---
description: Patterns kafka-python et Debezium CDC. Consumer, micro-batch, DLQ, offset management.
globs: "pipelines/daily_cdc_batch.py"
---

- `KafkaConsumer` avec `bootstrap_servers` depuis env
- Topics Debezium : `winstat.winstat.{TABLE}` (4 tables CDC)
- Micro-batch : accumule 500 events ou timeout 30s avant flush
- `auto_offset_reset='earliest'` pour ne pas perdre d'events
- `enable_auto_commit=False` : commit manuel apres flush Snowflake — sinon l'offset avance a la lecture et le message est perdu si INSERT echoue
- Deserialization : `json.loads(message.value)`
- Extraction payload Debezium : `after` (insert/update), `before` (delete)
- Operations CDC : `c` (create), `u` (update), `d` (delete), `r` (snapshot)
- Mapping operation : `c/r` -> `I`, `u` -> `U`, `d` -> `D`
- Metadonnees CDC : `cdc_operation`, `cdc_timestamp`, `cdc_schema`, `cdc_table`, `cdc_lsn`
- DLQ : events non traitables inseres dans `_DLQ` avec erreur — toujours ecrire dans DLQ avant `continue`, ne jamais ignorer un event silencieusement
- Graceful shutdown : `consumer.close()` dans le finally
- Timeout configurable via `CDC_BATCH_TIMEOUT_SEC`
