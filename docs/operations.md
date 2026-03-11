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

  ┌──────────────────────────────┬────────────────────────────────────────────┐
  │ Variable                     │ Description                                │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `ENV`                        │ Environnement (dev/prod)                   │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_ACCOUNT`          │ Compte Snowflake                           │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_USER`             │ Utilisateur Snowflake                      │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_PASSWORD`         │ Mot de passe Snowflake                     │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_DATABASE`         │ Base de donnees (defaut: MEDIcore)         │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_WAREHOUSE_NAME`   │ Warehouse (defaut: MEDIcore_WH)            │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `BATCH_INTERVAL_MIN`         │ Intervalle batch en minutes                │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `PHASE_TIMEOUT_SEC`          │ Timeout par phase (defaut: 1800)           │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `CDC_BATCH_TIMEOUT_SEC`      │ Timeout consumer Kafka (defaut: 30)        │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `TEAMS_WEBHOOK_URL`          │ Webhook Teams (optionnel)                  │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `ALERT_THRESHOLD`            │ Echecs avant alerte (defaut: 3)            │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `KAFKA_LAG_THRESHOLD`        │ Seuil lag Kafka en records (defaut: 10000) │
  └──────────────────────────────┴────────────────────────────────────────────┘

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

## Metabase (BI dashboards)

Metabase est une application BI open-source qui se connecte en lecture seule a Snowflake MARTS pour visualiser les 15 KPIs, 8 faits et 3 dimensions sur des dashboards interactifs.

### Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Navigateur web │────>│  Metabase (Java)     │────>│  Snowflake MARTS    │
│  localhost:3000 │     │  conteneur Docker    │     │  lecture seule      │
└─────────────────┘     │                      │     │  15 KPIs + 8 facts  │
                        │  Metadata stockee    │     │  + 3 dimensions     │
                        │  dans PostgreSQL     │     └─────────────────────┘
                        └──────────────────────┘
```

Metabase ne stocke aucune donnee metier — il fait des `SELECT` sur Snowflake a chaque requete. PostgreSQL stocke uniquement la config Metabase (dashboards, questions, comptes utilisateurs).

### Acces

```
http://localhost:3000
```

### Configuration Snowflake (premier lancement)

Au premier lancement, Metabase affiche un wizard de configuration :

1. Creer un compte admin Metabase
2. Ajouter la base de donnees Snowflake :

  ┌──────────────────┬────────────────────────────────────┐
  │ Parametre        │ Valeur                             │
  ├──────────────────┼────────────────────────────────────┤
  │ Type             │ Snowflake                          │
  ├──────────────────┼────────────────────────────────────┤
  │ Account          │ `SNOWFLAKE_ACCOUNT` (.env)         │
  ├──────────────────┼────────────────────────────────────┤
  │ User             │ Utilisateur avec role ANALYST      │
  ├──────────────────┼────────────────────────────────────┤
  │ Password         │ Mot de passe de l'utilisateur      │
  ├──────────────────┼────────────────────────────────────┤
  │ Database         │ MEDIcore                           │
  ├──────────────────┼────────────────────────────────────┤
  │ Schema           │ MARTS                              │
  ├──────────────────┼────────────────────────────────────┤
  │ Warehouse        │ MEDIcore_WH                        │
  ├──────────────────┼────────────────────────────────────┤
  │ Role             │ MEDICORE_ANALYST                   │
  └──────────────────┴────────────────────────────────────┘

3. Metabase scanne automatiquement les 26 tables MARTS

**Note** : le rôle `MEDICORE_ANALYST` et ses grants sont créés par `scripts/DDL_TABLES.sql`. L'assignation du rôle à un utilisateur reste manuelle :

```sql
GRANT ROLE MEDICORE_ANALYST TO USER <nom_utilisateur>;
```

### Ressources ajoutees

  ┌──────────────────┬────────┬────────┬──────────────────────────┐
  │ Service          │ RAM    │ CPU    │ Role                     │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ Metabase (Java)  │ 2 GB   │ 1 core │ Application BI           │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ PostgreSQL 16    │ 512 MB │ 0.5    │ Metadata Metabase        │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ Total ajoute     │ 2.5 GB │ 1.5    │                          │
  └──────────────────┴────────┴────────┴──────────────────────────┘

### Variables d'environnement

  ┌──────────────────────────┬──────────────────────────────────────┐
  │ Variable                 │ Description                          │
  ├──────────────────────────┼──────────────────────────────────────┤
  │ `METABASE_DB_PASSWORD`   │ Mot de passe PostgreSQL Metabase     │
  │                          │ (defaut: metabase_dev)               │
  └──────────────────────────┴──────────────────────────────────────┘

### Verification

```bash
# Verifier que les conteneurs tournent
docker ps | grep metabase

# Verifier la connexion Snowflake dans Metabase
# Admin > Databases > MEDIcore > Sync status = "done"
```

### Dashboards suggeres

Les 26 tables MARTS couvrent 16 dashboards thematiques :

  ┌─────┬──────────────────────────────────┬──────────────────────────────────────────────────────┐
  │  #  │ Dashboard                        │ Sources principales                                  │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  1  │ Vue d'ensemble pharmacie         │ mart_kpi_synthese_pharmacie                          │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  2  │ Marge detaillee                  │ mart_kpi_marge, dim_produit                          │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  3  │ Classification ABC (Pareto)      │ mart_kpi_abc, dim_produit                            │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  4  │ Stock et rotation                │ mart_kpi_stock, mart_kpi_stock_valorisation          │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  5  │ Ruptures et CA perdu             │ mart_kpi_ruptures, dim_produit                       │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  6  │ Ecoulement (sell-through)        │ mart_kpi_ecoulement, dim_fournisseur                 │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  7  │ Performance vendeurs             │ mart_kpi_operateur                                   │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  8  │ Tresorerie                       │ mart_kpi_tresorerie, fact_tresorerie                 │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │  9  │ Generiques et labos              │ mart_kpi_generique, dim_fournisseur                  │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 10  │ Univers (RX, OTC, PARA)          │ mart_kpi_univers                                     │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 11  │ Remises fournisseurs             │ mart_kpi_remise_labo, dim_fournisseur                │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 12  │ Produits dormants                │ mart_kpi_dormant, dim_fournisseur                    │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 13  │ Evolution CA                     │ mart_kpi_ca_evolution                                │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 14  │ Qualite des donnees              │ mart_kpi_qualite_donnees                             │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 15  │ Detail transactions (drill-down) │ fact_ventes, fact_commandes, dim_produit             │
  ├─────┼──────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ 16  │ Prix et mouvements stock         │ fact_prix_journalier, fact_stock_mouvement           │
  └─────┴──────────────────────────────────┴──────────────────────────────────────────────────────┘

Les dashboards sont a creer manuellement dans l'interface Metabase. Les 26/26 tables MARTS sont couvertes.
