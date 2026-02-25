# CDC Integration — MediCore ELT Pipeline

## Infrastructure CDC

- **Source** : MySQL 8.x (RDS), base `winstat`
- **Capture** : Debezium 2.7.3 via Kafka Connect
- **Transport** : Kafka 7.5.0 (Confluent)
- **Consumer** : `pipelines/daily_cdc_batch.py`

## Tables CDC (4)

  ┌─────────────┬─────────────────────────────┬──────────────────────────┐
  │ Table MySQL │         Topic Kafka         │       Clé primaire       │
  ├─────────────┼─────────────────────────────┼──────────────────────────┤
  │ `COMMANDES` │ `winstat.winstat.COMMANDES` │ PHA_ID, COM_GROI, PRD_ID │
  ├─────────────┼─────────────────────────────┼──────────────────────────┤
  │ `FACTURES`  │ `winstat.winstat.FACTURES`  │ PHA_ID, FAC_DATE, PRD_ID │
  ├─────────────┼─────────────────────────────┼──────────────────────────┤
  │ `ORDERS`    │ `winstat.winstat.ORDERS`    │ PHA_ID, ORD_ID           │
  ├─────────────┼─────────────────────────────┼──────────────────────────┤
  │ `MODSTOCK`  │ `winstat.winstat.MODSTOCK`  │ PHA_ID, MOD_DATE, PRD_ID │
  └─────────────┴─────────────────────────────┴──────────────────────────┘

## Flux CDC détaillé

1. **MySQL binlog** : Debezium lit les changements en temps réel
2. **Kafka topics** : events publiés au format JSON Debezium
3. **Consumer** (`daily_cdc_batch.py`) :
   - `KafkaConsumer` avec `auto_offset_reset='earliest'`
   - `enable_auto_commit=False` (commit manuel)
   - Accumule 500 events (ou timeout 30s)
   - Parse le payload Debezium
   - INSERT batch dans Snowflake RAW
   - Commit offset Kafka après flush réussi
4. **DLQ** : events malformés -> table `_DLQ` avec message d'erreur

## Format event Debezium

```json
{
  "payload": {
    "before": null,
    "after": {"PHA_ID": 123, "PRD_ID": 456, ...},
    "source": {"schema": "winstat", "table": "COMMANDES", "ts_ms": 1234567890},
    "op": "c",
    "ts_ms": 1234567890
  }
}
```

## Mapping opérations

  ┌───────────────┬─────────────────┬─────────────────────┐
  │ Debezium `op` │  Signification  │ `cdc_operation` RAW │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `c`           │ Create (insert) │ `I`                 │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `r`           │ Read (snapshot) │ `I`                 │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `u`           │ Update          │ `U`                 │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `d`           │ Delete          │ `D`                 │
  └───────────────┴─────────────────┴─────────────────────┘

## Métadonnées CDC ajoutées

  ┌─────────────────┬─────────────────┬────────────────────────────┐
  │     Colonne     │     Source      │        Description         │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_operation` │ `op` mappé      │ Type d'opération (I/U/D/S) │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_timestamp` │ `source.ts_ms`  │ Horodatage event MySQL     │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_schema`    │ `source.schema` │ Schéma source              │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_table`     │ `source.table`  │ Table source               │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_lsn`       │ `source.pos`    │ Position binlog            │
  └─────────────────┴─────────────────┴────────────────────────────┘

## Bulk load référence (14 tables)

- Exécution quotidienne à 03h00 via `batch_loop.sh`
- `bulk_load.py --ref-only --truncate`
- Flux : MySQL SELECT -> pandas DataFrame -> Parquet -> PUT @stage -> COPY INTO
- TRUNCATE avant reload (tables référence = snapshot complet)

## Monitoring CDC

- Source freshness dbt : warn 12h, error 24h (CDC), warn 36h, error 48h (référence)
- Alertes Teams après 3 échecs consécutifs
- Notification recovery automatique
- DLQ à surveiller régulièrement pour events non traités
