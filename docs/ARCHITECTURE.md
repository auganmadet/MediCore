# Architecture MediCore

## Flux de données global

```
┌───────────┐   binlog    ┌──────────┐         ┌─────────┐
│ MySQL RDS │───────────▶│ Debezium │────────▶│  Kafka  │
│ (winstat) │             │ (Connect)│         │ 4 topics│
└─────┬─────┘             └──────────┘         └────┬────┘
      │                                             │
      │  SELECT * (14 réf)                          │ consume (4 CDC)
      │                                             │
      ▼                                             ▼
┌─────────────┐                           ┌──────────────────┐
│ bulk_load.py│                           │daily_cdc_batch.py│
│ Parquet+PUT │                           │ Kafka→INSERT     │
└──────┬──────┘                           └────────┬─────────┘
       │                                           │
       └──────────────┬────────────────────────────┘
                      │ COPY INTO / INSERT
                      ▼
              ┌───────────────┐
              │ Snowflake RAW │  18 tables
              └───────┬───────┘
                      │ dbt run tag:staging
                      ▼
              ┌───────────────┐
              │ Snowflake STG │  18 modèles (dédup CDC + PII masking)
              └───────┬───────┘
                      │ dbt run tag:marts
                      ▼
              ┌───────────────┐
              │Snowflake MARTS│  3 dims + 8 facts
              └───────────────┘
```

## Layers Snowflake

### RAW Layer
- Données brutes depuis CDC (Kafka) et bulk load (MySQL SELECT)
- Colonnes metadata : CDC_OPERATION, CDC_TIMESTAMP, CDC_SCHEMA, CDC_TABLE, CDC_LSN
- CLUSTER BY (CDC_TIMESTAMP) sur les 4 tables CDC
- Aucune transformation

### STAGING Layer
- Déduplication CDC (ROW_NUMBER OVER PARTITION BY PK ORDER BY CDC_TIMESTAMP DESC)
- Filtre CDC_OPERATION != 'D' (exclut les deletes)
- PII masking (md5 sur colonnes sensibles : noms, adresses, téléphones)
- Renommage et cast colonnes

### MARTS Layer
- Star schema : dimensions + faits
- Dimensions avec membre par défaut INCONNU (SK = md5('-1' || '-' || '-1'))
- LEFT JOIN facts → dims avec COALESCE pour orphan rows
- Matérialisées en tables

## Services Docker

```
┌────────────────────┬───────────────────────────────────┬───────────────────────────────────┬──────────────────────────────┐
│ Service            │ Image                             │ Rôle                              │ Healthcheck                  │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ medicore_elt_batch │ Build local (Dockerfile)          │ Pipeline principal (batch_loop.sh)│ healthcheck.py (Snowflake)   │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ mysql_cdc          │ debezium/example-mysql:2.7.3      │ MySQL démo (Winstat local)        │ mysqladmin ping              │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ zookeeper          │ confluentinc/cp-zookeeper:7.7.0   │ Coordination Kafka                │ echo ruok                    │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ kafka              │ confluentinc/cp-kafka:7.5.0       │ Broker Kafka (4 topics CDC)       │ kafka-broker-api-versions    │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ kafka_connect      │ debezium/connect:2.7.3            │ Connecteur Debezium MySQL         │ curl REST API                │
├────────────────────┼───────────────────────────────────┼───────────────────────────────────┼──────────────────────────────┤
│ kafdrop            │ obsidiandynamics/kafdrop          │ UI monitoring topics              │ -                            │
└────────────────────┴───────────────────────────────────┴───────────────────────────────────┴──────────────────────────────┘
```

## Monitoring

- **Teams webhook** : alertes échec (seuil consécutif) + recovery
- **Source freshness** : CDC 12h warn / 24h error, référence 36h warn / 48h error
- **dbt test** : not_null, unique, relationships, expression_is_true (severity warn)
- **Docker healthcheck** : depends_on condition: service_healthy

## Fichiers clés

```
┌──────────────────────────────────┬────────────────────────────────────────────────────────────────┐
│ Fichier                          │ Rôle                                                           │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ scripts/setup.sh                 │ Premier lancement (HOST : DDL + Docker + Debezium)             │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ scripts/entrypoint.sh            │ Démarrage container (wait deps + dbt deps + cleanup lock)      │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ scripts/batch_loop.sh            │ Boucle principale (CDC + dbt + tests + freshness + alertes)    │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ pipelines/daily_cdc_batch.py     │ Consumer Kafka Debezium → INSERT RAW (4 tables)                │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ pipelines/bulk_load.py           │ MySQL SELECT → Parquet → COPY INTO RAW (18 tables)             │
├──────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ dbt/models/sources.yml           │ 18 sources RAW + freshness config                              │
└──────────────────────────────────┴────────────────────────────────────────────────────────────────┘
```
