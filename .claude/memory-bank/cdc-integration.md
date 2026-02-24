# CDC Integration — MediCore ELT Pipeline

## Infrastructure CDC

- **Source** : MySQL 8.x (RDS), base `winstat`
- **Capture** : Debezium 2.7.3 via Kafka Connect
- **Transport** : Kafka 7.5.0 (Confluent)
- **Consumer** : `pipelines/daily_cdc_batch.py`

## Tables CDC (4)

| Table MySQL | Topic Kafka | Cle primaire |
|-------------|------------|--------------|
| `COMMANDES` | `winstat.winstat.COMMANDES` | PHA_ID, COM_GROI, PRD_ID |
| `FACTURES` | `winstat.winstat.FACTURES` | PHA_ID, FAC_DATE, PRD_ID |
| `ORDERS` | `winstat.winstat.ORDERS` | PHA_ID, ORD_ID |
| `MODSTOCK` | `winstat.winstat.MODSTOCK` | PHA_ID, MOD_DATE, PRD_ID |

## Flux CDC detaille

1. **MySQL binlog** : Debezium lit les changements en temps reel
2. **Kafka topics** : events publies au format JSON Debezium
3. **Consumer** (`daily_cdc_batch.py`) :
   - `KafkaConsumer` avec `auto_offset_reset='earliest'`
   - `enable_auto_commit=False` (commit manuel)
   - Accumule 500 events (ou timeout 30s)
   - Parse le payload Debezium
   - INSERT batch dans Snowflake RAW
   - Commit offset Kafka apres flush reussi
4. **DLQ** : events malformes -> table `_DLQ` avec message d'erreur

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

## Mapping operations

| Debezium `op` | Signification | `cdc_operation` RAW |
|---------------|--------------|---------------------|
| `c` | Create (insert) | `I` |
| `r` | Read (snapshot) | `I` |
| `u` | Update | `U` |
| `d` | Delete | `D` |

## Metadonnees CDC ajoutees

| Colonne | Source | Description |
|---------|--------|-------------|
| `cdc_operation` | `op` mappe | Type d'operation (I/U/D/S) |
| `cdc_timestamp` | `source.ts_ms` | Horodatage event MySQL |
| `cdc_schema` | `source.schema` | Schema source |
| `cdc_table` | `source.table` | Table source |
| `cdc_lsn` | `source.pos` | Position binlog |

## Bulk load reference (14 tables)

- Execution quotidienne a 03h00 via `batch_loop.sh`
- `bulk_load.py --ref-only --truncate`
- Flux : MySQL SELECT -> pandas DataFrame -> Parquet -> PUT @stage -> COPY INTO
- TRUNCATE avant reload (tables reference = snapshot complet)

## Monitoring CDC

- Source freshness dbt : warn 12h, error 24h (CDC), warn 36h, error 48h (reference)
- Alertes Teams apres 3 echecs consecutifs
- Notification recovery automatique
- DLQ a surveiller regulierement pour events non traites
