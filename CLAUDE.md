# CLAUDE.md — MediCore ELT Pipeline

## Protocole de chargement

### 1. Standards et règles

Les règles sont dans `.claude/rules/` (chargées automatiquement par Claude Code selon les globs).
Consulter `.claude/rules-index.md` pour une vue d'ensemble.

### 2. Memory Bank

Consulter `.claude/memory-bank/index.md` pour l'organisation par tiers.
Charger les documents selon le type de tâche :

- **Tier 1** (toujours) : `getting-started.md`, `architecture.md`
- **Tier 2** (domaine) : `data-model.md`, `tech-stack.md`, `development.md`, `security.md`
- **Tier 3** (feature) : `cdc-integration.md`, `dbt-transformations.md`

### 3. Dev Memories

**Ne JAMAIS lire sans demande explicite de l'utilisateur.**
Répertoire : `.claude/dev-memories/`

---

## Référence rapide

### Architecture

- **Type** : Pipeline ELT industrialisé pour données pharmacie
- **Flux** : MySQL RDS -> Kafka CDC -> Snowflake RAW -> dbt STG -> dbt MARTS
- **Sources** : 18 tables (4 CDC + 14 référence)
- **Transformations** : dbt 1.8 (SQL/Jinja2)
- **DWH** : Snowflake (RAW -> STAGING -> MARTS)
- **Streaming** : Debezium 2.7.3 + Kafka 7.5.0
- **Infra** : Docker Compose (6 services)
- **Monitoring** : Teams webhook + dbt source freshness

### Composants clés

  ┌───────────────────────────────────┬───────────────────────────────────────────────────────┐
  │              Module               │                         Rôle                          │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `pipelines/daily_cdc_batch.py`    │ Consumer Kafka -> INSERT Snowflake RAW (4 tables CDC) │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `pipelines/bulk_load.py`          │ MySQL SELECT -> Parquet -> COPY INTO RAW (18 tables)  │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `pipelines/diagnose_recover.py`   │ Diagnostic et recovery                                │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/models/staging/stg_*.sql`    │ Dédup CDC + PII masking (18 modèles)                  │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/models/marts/dim_*.sql`      │ 3 dimensions (pharmacie, produit, fournisseur)        │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/models/marts/fact_*.sql`     │ 8 faits (ventes, commandes, stock, ruptures...)       │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/models/marts/mart_kpi_*.sql` │ 9 KPIs métier (marge, écoulement, ABC, stock...)      │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/macros/pii_masking.sql`      │ Macros masquage PII (MD5)                             │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `scripts/batch_loop.sh`           │ Orchestration principale (boucle 5-30 min)            │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `scripts/setup.sh`                │ Setup initial (Docker + DDL + Debezium)               │
  └───────────────────────────────────┴───────────────────────────────────────────────────────┘

### Sécurité critique

- PII masquées par MD5 dans staging (noms, adresses, téléphones)
- Requêtes paramétrées exclusivement dans les pipelines Python
- Pas d'interpolation de chaînes dans les requêtes SQL
- Credentials via `.env` (non versionné)
- Rôle Snowflake `MEDIcore_DBT_EXECUTOR` pour isolation

### Commandes essentielles

```bash
docker compose up -d                     # Démarrer tous les services
docker exec -it medicore_elt_batch bash  # Shell dans le conteneur
dbt run --select tag:staging             # Lancer staging
dbt run --select tag:marts               # Lancer marts
dbt test --select stg_*                  # Tests staging
dbt source freshness                     # Vérifier fraîcheur
python pipelines/bulk_load.py            # Bulk load complet
python pipelines/daily_cdc_batch.py      # Consumer CDC
```

### Conventions

- **Code** : Anglais
- **Commentaires/Docstrings** : Français (Google-style)
- **Messages monitoring** : Français
- **Commits** : Français, atomiques, concis
- **Branches** : kebab-case (`feature/xxx`, `fix/xxx`)
- **SQL/dbt** : UPPERCASE pour mots-clés, snake_case pour colonnes

### Couches de données

  ┌─────────┬───────────┬────────────────────┬─────────────────────────────────────────┐
  │ Couche  │  Schéma   │  Matérialisation   │               Description               │
  ├─────────┼───────────┼────────────────────┼─────────────────────────────────────────┤
  │ RAW     │ `RAW`     │ Tables             │ Copie brute MySQL + métadonnées CDC     │
  ├─────────┼───────────┼────────────────────┼─────────────────────────────────────────┤
  │ STAGING │ `STAGING` │ Views/Incremental  │ Dédup CDC + PII masking + typage        │
  ├─────────┼───────────┼────────────────────┼─────────────────────────────────────────┤
  │ MARTS   │ `MARTS`   │ Tables/Incremental │ Dimensions + Faits + KPIs (star schema) │
  └─────────┴───────────┴────────────────────┴─────────────────────────────────────────┘

### 4 Tables CDC

`COMMANDES` | `FACTURES` | `ORDERS` | `MODSTOCK`

### 14 Tables référence

`DAYBYDAY` | `EAN13` | `FOURNISSEURS` | `HISTORY` | `LOG` | `LPPR` | `OPERATEUR` | `PHARMACIE` | `PRODUITS` | `QUANTHEB` | `REMISE` | `STOCK` | `TRESORERIE` | `VENTEPRD`
