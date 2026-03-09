# Guide operationnel MediCore

## Demarrage

```bash
# Premier lancement (DDL + Docker + Debezium connector)
./scripts/setup.sh

# Lancement quotidien
docker compose up -d
```

## Architecture du batch

Le conteneur `medicore_elt_batch` execute `batch_loop.sh` en boucle (5 min dev / 30 min prod).

Chaque iteration :

  ┌───────┬──────────────────────────────────────────────────────┐
  │ Phase │ Description                                          │
  ├───────┼──────────────────────────────────────────────────────┤
  │   0   │ Re-bulk reference (14 tables, 1x/jour a 03h)         │
  ├───────┼──────────────────────────────────────────────────────┤
  │   1   │ CDC Kafka -> Snowflake RAW (4 tables)                │
  ├───────┼──────────────────────────────────────────────────────┤
  │   2   │ dbt run staging (dedup + PII masking)                │
  ├───────┼──────────────────────────────────────────────────────┤
  │   3   │ dbt snapshot (SCD2)                                  │
  ├───────┼──────────────────────────────────────────────────────┤
  │   4a  │ dbt run marts (dimensions + faits + KPIs)            │
  ├───────┼──────────────────────────────────────────────────────┤
  │   4b  │ dbt test staging + marts                             │
  ├───────┼──────────────────────────────────────────────────────┤
  │   5   │ dbt source freshness                                 │
  └───────┴──────────────────────────────────────────────────────┘

## Lineage operationnel (AUDIT)

Chaque iteration genere un `RUN_ID` UUID. Les resultats sont persistes dans `MEDICORE.AUDIT` :

```sql
-- Derniers runs
SELECT * FROM MEDICORE.AUDIT.PIPELINE_RUNS ORDER BY RUN_START DESC LIMIT 10;

-- Detail des etapes d'un run
SELECT * FROM MEDICORE.AUDIT.PIPELINE_STEP_RUNS WHERE RUN_ID = '<uuid>' ORDER BY STEP_START;

-- Resultats dbt par run
SELECT * FROM MEDICORE.AUDIT.DBT_MODEL_RUNS WHERE RUN_ID = '<uuid>';

-- Vue resume
SELECT * FROM MEDICORE.AUDIT.AUDIT_RUN_SUMMARY ORDER BY RUN_START DESC LIMIT 10;

-- Lag Kafka par topic (derniers runs)
SELECT * FROM MEDICORE.AUDIT.CDC_LAG_METRICS ORDER BY CREATED_AT DESC LIMIT 20;

-- Statistiques lag pour calibrer le seuil
SELECT AVG(LAG), MAX(LAG), PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY LAG)
FROM MEDICORE.AUDIT.CDC_LAG_METRICS;
```

Retention automatique : 90 jours (purge quotidienne a 01h).

## Monitoring et alertes

  ┌───────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Mecanisme                 │ Configuration                                            │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Teams webhook             │ `TEAMS_WEBHOOK_URL` (.env)                               │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Seuil alerte              │ `ALERT_THRESHOLD` (defaut: 3)                            │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Freshness CDC             │ warn 12h / error 24h                                     │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Freshness reference       │ warn 36h / error 48h                                     │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Volume CDC                │ Alerte apres N batches a 0 events                        │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Lag Kafka                 │ Alerte si lag > `KAFKA_LAG_THRESHOLD` N fois consecutives │
  └───────────────────────────┴──────────────────────────────────────────────────────────┘

Le **lag Kafka** mesure le retard du consumer CDC (end_offset - committed_offset). Un lag croissant signifie que le consumer ne suit pas le rythme de Debezium. Les metriques sont ecrites dans `/tmp/cdc_lag_metrics` et historisees dans `AUDIT.CDC_LAG_METRICS`.

## Diagnostic et recovery

```bash
# Diagnostic seul (lecture seule)
docker exec medicore_elt_batch python pipelines/diagnose_recover.py

# Diagnostic + correction automatique
docker exec medicore_elt_batch python pipelines/diagnose_recover.py --fix
```

Detecte : processus zombies, tables vides, doublons, timestamps invalides.

## Variables d'environnement

  ┌──────────────────────────────┬─────────────────────────────────────────┐
  │ Variable                     │ Description                             │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `ENV`                        │ Environnement (dev/prod)                │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `SNOWFLAKE_ACCOUNT`          │ Compte Snowflake                        │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `SNOWFLAKE_USER`             │ Utilisateur Snowflake                   │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `SNOWFLAKE_PASSWORD`         │ Mot de passe Snowflake                  │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `SNOWFLAKE_DATABASE`         │ Base de donnees (defaut: MEDIcore)      │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `SNOWFLAKE_WAREHOUSE_NAME`   │ Warehouse (defaut: MEDIcore_WH)        │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `BATCH_INTERVAL_MIN`         │ Intervalle batch en minutes             │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `PHASE_TIMEOUT_SEC`          │ Timeout par phase (defaut: 1800)        │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `CDC_BATCH_TIMEOUT_SEC`      │ Timeout consumer Kafka (defaut: 30)     │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `TEAMS_WEBHOOK_URL`          │ Webhook Teams (optionnel)               │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `ALERT_THRESHOLD`            │ Echecs avant alerte (defaut: 3)         │
  ├──────────────────────────────┼─────────────────────────────────────────┤
  │ `KAFKA_LAG_THRESHOLD`        │ Seuil lag Kafka en records (defaut: 10000) │
  └──────────────────────────────┴─────────────────────────────────────────┘

## Commandes utiles

```bash
# Shell dans le conteneur
docker exec -it medicore_elt_batch bash

# Logs en temps reel
docker logs -f medicore_elt_batch

# Bulk load manuel (toutes les tables)
docker exec medicore_elt_batch python pipelines/bulk_load.py --truncate

# Bulk load reference uniquement
docker exec medicore_elt_batch python pipelines/bulk_load.py --ref-only --truncate

# Consumer CDC manuel
docker exec medicore_elt_batch python pipelines/daily_cdc_batch.py

# dbt commands
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt run --select tag:staging"
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt test --select stg_*"
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt source freshness"

# Kafdrop (UI Kafka)
# http://localhost:9000
```

## Arret propre

```bash
# Arret graceful (attend la fin de la phase en cours)
docker compose stop medicore-elt-batch

# Arret complet
docker compose down
```

Le conteneur intercepte SIGTERM et termine proprement apres la phase en cours.
