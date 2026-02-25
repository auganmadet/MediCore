---
description: Patterns kafka-python et Debezium CDC. Consumer, micro-batch, DLQ, offset management.
globs: "pipelines/*cdc*.py,pipelines/*kafka*.py,pipelines/*consumer*.py"
---

- `KafkaConsumer` avec `bootstrap_servers` depuis env
- Topics Debezium : `winstat.winstat.{TABLE}` (4 tables CDC)
- Micro-batch : accumule 500 events ou timeout 30s avant flush
- `auto_offset_reset='earliest'` pour ne pas perdre d'events
- `enable_auto_commit=False` : commit manuel après flush Snowflake — sinon l'offset avance à la lecture et le message est perdu si INSERT échoue
- Désérialisation : `json.loads(message.value)`
- Extraction payload Debezium : `after` (insert/update), `before` (delete)
- Opérations CDC : `c` (create), `u` (update), `d` (delete), `r` (snapshot)
- Mapping opération : `c/r` -> `I`, `u` -> `U`, `d` -> `D`
- Métadonnées CDC : `cdc_operation`, `cdc_timestamp`, `cdc_schema`, `cdc_table`, `cdc_lsn`
- DLQ : events non traitables insérés dans `_DLQ` avec erreur — toujours écrire dans DLQ avant `continue`, ne jamais ignorer un event silencieusement
- Graceful shutdown : `consumer.close()` dans le finally
- Timeout configurable via `CDC_BATCH_TIMEOUT_SEC`
