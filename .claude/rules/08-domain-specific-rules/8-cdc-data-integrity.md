---
description: Intégrité des données CDC. Déduplication, DLQ, recovery, cohérence.
globs: "pipelines/**/*.py,dbt/models/staging/**/*.sql"
---

- Opérations CDC Debezium : `c` (create), `u` (update), `d` (delete), `r` (snapshot)
- Mapping : `c/r` -> `I` (insert), `u` -> `U` (update), `d` -> `D` (delete)
- Dédup staging : `ROW_NUMBER() OVER (PARTITION BY PK ORDER BY cdc_timestamp DESC)`
- Filtre deletes : `WHERE cdc_operation != 'D'` dans staging
- Métadonnées CDC préservées dans RAW : `cdc_operation`, `cdc_timestamp`, `cdc_lsn`
- DLQ (`_DLQ`) pour events malformés ou non traitables
- Bulk load référence : CLONE+SWAP + reload quotidien (23h FR / 21h UTC)
- Incremental staging : `cdc_timestamp >= max(loaded_at)` pour éviter les retraitements
- Commit Kafka manuel après flush Snowflake réussi
- `diagnose_recover.py` pour diagnostic et reprise en cas d'incident
- Monitoring : seuils freshness CDC 12h/24h, référence 36h/48h
- Alertes Teams sur 3 échecs consécutifs + notification recovery
- Monitorer le volume CDC après chaque batch — alerter après N batches consécutifs à 0 events (topic vide != erreur mais peut indiquer un problème Debezium/Kafka)
