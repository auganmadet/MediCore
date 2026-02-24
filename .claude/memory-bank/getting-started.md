# Getting Started — MediCore ELT Pipeline

## Prerequis

- Docker et Docker Compose
- Acces a une instance MySQL RDS (base `winstat`)
- Compte Snowflake avec role `MEDIcore_DBT_EXECUTOR`
- Webhook Microsoft Teams (optionnel, pour monitoring)

## Premier lancement

```bash
# 1. Configurer les credentials
cp .env.example .env
# Editer .env avec les identifiants reels

# 2. Setup complet (DDL Snowflake + Docker + Debezium connector)
bash scripts/setup.sh

# 3. Demarrer tous les services
docker compose up -d

# 4. Verifier le statut
docker compose ps
docker logs medicore_elt_batch --tail 50
```

Le conteneur `medicore_elt_batch` demarre automatiquement la boucle batch.

## Configuration (.env)

| Variable | Description |
|----------|-------------|
| `SNOWFLAKE_ACCOUNT` | Identifiant du compte Snowflake |
| `SNOWFLAKE_USER` | Utilisateur Snowflake |
| `SNOWFLAKE_PASSWORD` | Mot de passe Snowflake |
| `MYSQL_HOST` | Hote MySQL RDS |
| `MYSQL_PORT` | Port MySQL (defaut 3306) |
| `MYSQL_USER` | Utilisateur MySQL |
| `MYSQL_PASSWORD` | Mot de passe MySQL |
| `MYSQL_DATABASE` | Base source (winstat) |
| `KAFKA_BOOTSTRAP_SERVERS` | Serveurs Kafka (defaut kafka:9092) |
| `TEAMS_WEBHOOK_URL` | URL webhook Teams pour alertes |
| `CDC_BATCH_TIMEOUT_SEC` | Timeout micro-batch CDC (defaut 30) |
| `BATCH_INTERVAL` | Intervalle boucle en secondes (defaut 300) |

## Commandes essentielles

| Commande | Action |
|----------|--------|
| `docker compose up -d` | Demarrer tous les services |
| `docker compose down` | Arreter tous les services |
| `docker exec -it medicore_elt_batch bash` | Shell dans le conteneur |
| `dbt run --select tag:staging` | Lancer les modeles staging |
| `dbt run --select tag:marts` | Lancer les modeles marts |
| `dbt test` | Executer tous les tests |
| `dbt source freshness` | Verifier la fraicheur des sources |
| `python pipelines/bulk_load.py` | Bulk load complet (18 tables) |
| `python pipelines/bulk_load.py --ref-only --truncate` | Reload reference (14 tables) |
| `python pipelines/daily_cdc_batch.py` | Consumer CDC Kafka |
| `python pipelines/diagnose_recover.py` | Diagnostic et recovery |

## Dependances Python

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

## Depannage

- **Erreur connexion Snowflake** : Verifier `.env` et que le role/warehouse existent
- **Kafka non pret** : Attendre que les health checks passent (`docker compose ps`)
- **Pas de donnees CDC** : Verifier le connecteur Debezium (`curl connect:8083/connectors`)
- **dbt echoue** : Verifier `dbt debug` et `profiles.yml`
- **Tables vides** : Executer `bulk_load.py` pour le chargement initial
