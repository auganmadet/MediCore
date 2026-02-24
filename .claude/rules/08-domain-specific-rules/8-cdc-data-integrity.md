---
description: Integrite des donnees CDC. Deduplication, DLQ, recovery, coherence.
globs: "pipelines/**/*.py,dbt/models/staging/**/*.sql"
---

- Operations CDC Debezium : `c` (create), `u` (update), `d` (delete), `r` (snapshot)
- Mapping : `c/r` -> `I` (insert), `u` -> `U` (update), `d` -> `D` (delete)
- Dedup staging : `ROW_NUMBER() OVER (PARTITION BY PK ORDER BY cdc_timestamp DESC)`
- Filtre deletes : `WHERE cdc_operation != 'D'` dans staging
- Metadonnees CDC preservees dans RAW : `cdc_operation`, `cdc_timestamp`, `cdc_lsn`
- DLQ (`_DLQ`) pour events malformes ou non traitables
- Bulk load reference : `TRUNCATE` + reload quotidien (03h00)
- Incremental staging : `cdc_timestamp >= max(loaded_at)` pour eviter les retraitements
- Commit Kafka manuel apres flush Snowflake reussi
- `diagnose_recover.py` pour diagnostic et reprise en cas d'incident
- Monitoring : seuils freshness CDC 12h/24h, reference 36h/48h
- Alertes Teams sur 3 echecs consecutifs + notification recovery
- Monitorer le volume CDC apres chaque batch — alerter apres N batches consecutifs a 0 events (topic vide != erreur mais peut indiquer un probleme Debezium/Kafka)
