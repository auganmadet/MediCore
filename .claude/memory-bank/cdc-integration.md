# CDC Integration — MediCore ELT Pipeline

## Infrastructure CDC

- **Source** : MySQL 8.x (RDS ou Docker local), base `winstat`
- **Capture** : Debezium 2.7.3 via Kafka Connect
- **Transport** : Kafka 7.5.0 (Confluent) avec dual listeners
- **Consumer** : `pipelines/daily_cdc_batch.py`

## Configuration Kafka (dual listeners)

Pour supporter à la fois les conteneurs Docker et l'accès depuis WSL/host :

```yaml
# docker-compose.yml
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
KAFKA_LISTENERS: INTERNAL://0.0.0.0:29092,EXTERNAL://0.0.0.0:9092
KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:29092,EXTERNAL://localhost:9092
KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
```

| Listener | Port | Usage |
|----------|------|-------|
| INTERNAL | 29092 | Conteneurs Docker (kafka:29092) |
| EXTERNAL | 9092 | Host WSL/Windows (localhost:9092) |

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
  │ `r`           │ Read (snapshot) │ `S`                 │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `u`           │ Update          │ `U`                 │
  ├───────────────┼─────────────────┼─────────────────────┤
  │ `d`           │ Delete          │ `D`                 │
  └───────────────┴─────────────────┴─────────────────────┘

**Note** : Les messages tombstone (null value) sont ignorés par le consumer.

## Métadonnées CDC ajoutées

  ┌─────────────────┬─────────────────┬────────────────────────────┐
  │     Colonne     │     Source      │        Description         │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_operation` │ `op` mappé      │ Type d'opération (I/U/D/S) │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_timestamp` │ `source.ts_ms`  │ Horodatage event MySQL     │
  ├─────────────────┼─────────────────┼────────────────────────────┤
  │ `cdc_lsn`       │ `source.pos`    │ Position binlog            │
  └─────────────────┴─────────────────┴────────────────────────────┘

## Bulk load référence (14 tables)

- Exécution quotidienne à 23h FR (21h UTC) via `batch_loop.sh` avec logique hebdomadaire (depuis 2026-04-23) :
  - **Dimanche (DOW=0)** : SKIP (pharmacies fermées).
  - **Lundi (DOW=1)** : FULL reload (`bulk_load.py --ref-only --truncate`) avec pattern CLONE+SWAP sur les 14 tables.
  - **Mardi→Samedi (DOW=2..6)** : mode INCREMENTAL (`bulk_load.py --ref-only --truncate --incremental-days 30`) sur 4 tables candidates + TRUNCATE classique sur les 10 autres.
- Flux classique (full) : MySQL SELECT → pandas DataFrame → Parquet → PUT @stage → COPY INTO.
- Flux incremental : filtre MySQL `WHERE date_col >= CURDATE() - INTERVAL 30 DAY` → MERGE INTO via table staging `_STG_INCR`.
- CLONE+SWAP avant TRUNCATE en mode full (rollback automatique si count=0).

### 4 tables candidates incremental (`INCREMENTAL_TABLES`)

  ┌──────────────────────┬────────────────────┬──────────────────────────────────┐
  │ Table MySQL          │ Colonne date       │ Clé primaire                     │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┤
  │ `MEDIPRIX_FACTURES`  │ `FAC_DATE`         │ PHA_ID, FAC_ID, FAC_TI           │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┤
  │ `STOCKHISTORY`       │ `STH_DATE`         │ PHA_ID, PRD_ID, STH_DATE         │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┤
  │ `DAYBYDAY`           │ `DBD_DATE`         │ PHA_ID, DBD_DATE, PRD_ID         │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┤
  │ `MANQHISTORY`        │ `MNQ_DATE`         │ PHA_ID, MNQ_DATE, PRD_ID, FAC_ID │
  └──────────────────────┴────────────────────┴──────────────────────────────────┘

Gain : ref_reload incremental ~16 min vs full ~4h48 (gain ~-391 EUR/mois).

## Monitoring CDC

- Source freshness dbt : warn 12h, error 24h (CDC), warn 36h, error 48h (référence)
- Alertes Teams après 3 échecs consécutifs
- Notification recovery automatique
- DLQ à surveiller régulièrement pour events non traités

## Tests CDC (run_all_tests.sh)

Script de tests complet et idempotent : `scripts/run_all_tests.sh`

```bash
# Lancer les tests avec mesure du temps (~6-7 min)
cd /mnt/c/Temp/MediCore && STARTTIME=$(date +%s) && ./scripts/run_all_tests.sh 2>&1; echo "=== Durée: $(($(date +%s) - STARTTIME))s ==="
```

### Étapes du script

| Étape | Description | Vérification |
|-------|-------------|--------------|
| 1/6 | pytest (113 tests unitaires) | Tous les tests passent |
| 2/6 | bulk_load | SKIP (déjà chargé) |
| 3/6 | CDC INSERT | `cdc_operation = 'I'` |
| 4/6 | CDC UPDATE | `cdc_operation = 'U'` |
| 5/6 | CDC DELETE | `cdc_operation = 'D'` |
| 6/6 | dbt build | PASS (293 modèles) |

### Variables d'environnement CDC (host WSL)

```bash
CDC_KAFKA_TOPIC_PREFIX=winstat.winstat
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
CDC_BATCH_TIMEOUT_SEC=30
```

### Données de test (IDs fictifs)

```bash
TEST_PHA_ID=99999
TEST_COM_GROI=999999999
TEST_PRD_ID=888888
```

Ces données sont automatiquement nettoyées (MySQL + Snowflake) avant et après les tests.
