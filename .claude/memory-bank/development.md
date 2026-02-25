# Development — MediCore ELT Pipeline

## Environnement

```bash
# Démarrer les services Docker
docker compose up -d

# Shell dans le conteneur principal
docker exec -it medicore_elt_batch bash

# Installer les dépendances localement (hors Docker)
pip install -r requirements.txt
```

## Commandes

  ┌─────────────────────────────────────────────┬────────────────────────────────┐
  │                  Commande                   │          Description           │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `docker compose up -d`                      │ Démarrer tous les services     │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `docker compose down`                       │ Arrêter tous les services      │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `docker compose ps`                         │ Statut des services            │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `docker logs medicore_elt_batch --tail 100` │ Logs du conteneur principal    │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt run --select tag:staging`              │ Lancer les modèles staging     │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt run --select tag:marts`                │ Lancer les modèles marts       │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt run --select model_name`               │ Lancer un modèle spécifique    │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt test`                                  │ Exécuter tous les tests        │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt test --select stg_*`                   │ Tests staging uniquement       │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt source freshness`                      │ Vérifier fraîcheur des sources │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `dbt debug`                                 │ Diagnostic connexion dbt       │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `python pipelines/bulk_load.py`             │ Bulk load complet              │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `python pipelines/daily_cdc_batch.py`       │ Consumer CDC                   │
  ├─────────────────────────────────────────────┼────────────────────────────────┤
  │ `python pipelines/diagnose_recover.py`      │ Diagnostic et recovery         │
  └─────────────────────────────────────────────┴────────────────────────────────┘

## Structure des modules

```
docker-compose.yml              -> 6 services Docker
Dockerfile                      -> Image multi-stage Python 3.11 + dbt
requirements.txt                -> Dépendances Python
.env                            -> Credentials (non versionné)

pipelines/daily_cdc_batch.py    -> Consumer Kafka micro-batch (4 tables CDC)
pipelines/bulk_load.py          -> MySQL -> Parquet -> COPY INTO (18 tables)
pipelines/diagnose_recover.py   -> Diagnostic et reprise
pipelines/utils/pii_masking.py  -> PII masking legacy (déplacé vers dbt)

dbt/dbt_project.yml             -> Config projet dbt
dbt/profiles.yml                -> Profils connexion Snowflake
dbt/models/sources.yml          -> 18 sources RAW + freshness
dbt/models/staging/stg_*.sql    -> 18 modèles staging
dbt/models/staging/_staging.yml -> Tests staging
dbt/models/marts/dim_*.sql      -> 3 dimensions
dbt/models/marts/fact_*.sql     -> 8 faits
dbt/models/marts/mart_kpi_*.sql -> KPIs métier
dbt/models/marts/_marts.yml     -> Tests marts
dbt/macros/pii_masking.sql      -> Macro masquage PII

scripts/setup.sh                -> Setup initial complet
scripts/entrypoint.sh           -> Démarrage conteneur
scripts/batch_loop.sh           -> Boucle orchestration
scripts/healthcheck.py          -> Health check Snowflake
scripts/DDL_WH.sql              -> DDL warehouse et rôles
scripts/DDL_TABLES.sql          -> DDL 18 tables RAW
```

## Conventions

- **Code Python** : Anglais (noms de variables, classes, fonctions)
- **Commentaires/Docstrings** : Français, style Google
- **SQL/dbt** : UPPERCASE mots-clés, snake_case colonnes
- **Messages monitoring** : Français
- **Commits** : Français, atomiques, concis
- **Branches** : kebab-case, descriptives (`feature/xxx`, `fix/xxx`)

## Workflow Git

- Branches : `main`, `feature/xxx`, `fix/xxx`
- Messages de commit en français, simples et atomiques
- Ne jamais mentionner Claude ou l'IA comme auteur
- Ne jamais commiter `.env` ou credentials
- Nettoyer l'historique avant merge

## Ajout d'une nouvelle table source

1. Ajouter la table dans `scripts/DDL_TABLES.sql` (RAW)
2. Ajouter le mapping dans `bulk_load.py`
3. Si CDC : ajouter le topic dans `daily_cdc_batch.py`
4. Ajouter la source dans `dbt/models/sources.yml` (+ freshness)
5. Créer le modèle staging `dbt/models/staging/stg_xxx.sql`
6. Ajouter les tests dans `_staging.yml`
7. Créer les modèles marts si nécessaire
8. Mettre à jour la memory-bank

## Ajout d'un KPI métier

1. Créer le modèle `dbt/models/marts/mart_kpi_xxx.sql`
2. Référencer les dimensions et faits via `{{ ref() }}`
3. Ajouter les tests dans `_marts.yml`
4. Documenter dans `docs/KPIs.md`

## Logs

- Docker logs : `docker logs <service> --tail N`
- Logs applicatifs : `logs/`
- Audit : `audit/logs/`, `audit/checksums/`, `audit/lineage/`
