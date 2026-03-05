# Getting Started — MediCore ELT Pipeline

## Prérequis

- Docker et Docker Compose
- Accès à une instance MySQL RDS (base `winstat`)
- Compte Snowflake avec rôle `MEDICORE_DBT_EXECUTOR`
- Webhook Microsoft Teams (optionnel, pour monitoring)

## Premier lancement

```bash
# 1. Configurer les credentials
cp .env.example .env
# Éditer .env avec les identifiants réels

# 2. Setup complet (DDL Snowflake + Docker + Debezium connector)
bash scripts/setup.sh

# 3. Démarrer tous les services
docker compose up -d

# 4. Vérifier le statut
docker compose ps
docker logs medicore_elt_batch --tail 50
```

Le conteneur `medicore_elt_batch` démarre automatiquement la boucle batch.

## Configuration (.env)

  ┌───────────────────────────┬────────────────────────────────────────────┐
  │         Variable          │                Description                 │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_ACCOUNT`       │ Identifiant du compte Snowflake            │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_USER`          │ Utilisateur Snowflake                      │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_PASSWORD`      │ Mot de passe Snowflake                     │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `MYSQL_HOST`              │ Hôte MySQL RDS                             │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `MYSQL_PORT`              │ Port MySQL (défaut 3306)                   │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `MYSQL_USER`              │ Utilisateur MySQL                          │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `MYSQL_PASSWORD`          │ Mot de passe MySQL                         │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `MYSQL_DATABASE`          │ Base source (winstat)                      │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `KAFKA_BOOTSTRAP_SERVERS` │ Serveurs Kafka (défaut kafka:9092)         │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `TEAMS_WEBHOOK_URL`       │ URL webhook Teams pour alertes             │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `CDC_BATCH_TIMEOUT_SEC`   │ Timeout micro-batch CDC (défaut 30)        │
  ├───────────────────────────┼────────────────────────────────────────────┤
  │ `BATCH_INTERVAL`          │ Intervalle boucle en secondes (défaut 300) │
  └───────────────────────────┴────────────────────────────────────────────┘

## Commandes essentielles

  ┌───────────────────────────────────────────────────────┬───────────────────────────────────┐
  │                       Commande                        │              Action               │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `docker compose up -d`                                │ Démarrer tous les services        │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `docker compose down`                                 │ Arrêter tous les services         │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `docker exec -it medicore_elt_batch bash`             │ Shell dans le conteneur           │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `dbt run --select tag:staging`                        │ Lancer les modèles staging        │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `dbt run --select tag:marts`                          │ Lancer les modèles marts          │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `dbt test`                                            │ Exécuter tous les tests           │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `dbt source freshness`                                │ Vérifier la fraîcheur des sources │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `python pipelines/bulk_load.py`                       │ Bulk load complet (18 tables)     │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `python pipelines/bulk_load.py --ref-only --truncate` │ Reload référence (14 tables)      │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `python pipelines/daily_cdc_batch.py`                 │ Consumer CDC Kafka                │
  ├───────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ `python pipelines/diagnose_recover.py`                │ Diagnostic et recovery            │
  └───────────────────────────────────────────────────────┴───────────────────────────────────┘

## Dépendances Python

```
snowflake-connector-python[pandas]==3.12.4
mysql-connector-python==8.4.0
kafka-python==2.0.2
pandas==2.1.4
pyarrow==14.0.1
dbt-core==1.8.0
dbt-snowflake==1.8.0
requests==2.31.0
pyyaml==6.0.1
python-dotenv==1.0.0
```

## Dépannage

- **Erreur connexion Snowflake** : Vérifier `.env` et que le rôle/warehouse existent
- **Kafka non prêt** : Attendre que les health checks passent (`docker compose ps`)
- **Pas de données CDC** : Vérifier le connecteur Debezium (`curl connect:8083/connectors`)
- **dbt échoue** : Vérifier `dbt debug` et `profiles.yml`
- **Tables vides** : Exécuter `bulk_load.py` pour le chargement initial
