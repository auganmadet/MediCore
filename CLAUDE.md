# CLAUDE.md — MediCore ELT Pipeline

## Protocole de chargement

### 1. Standards et regles

Les regles sont dans `.claude/rules/` (chargees automatiquement par Claude Code selon les globs).
Consulter `.claude/rules-index.md` pour une vue d'ensemble.

### 2. Memory Bank

Consulter `.claude/memory-bank/index.md` pour l'organisation par tiers.
Charger les documents selon le type de tache :

- **Tier 1** (toujours) : `getting-started.md`, `architecture.md`
- **Tier 2** (domaine) : `data-model.md`, `tech-stack.md`, `development.md`, `security.md`
- **Tier 3** (feature) : `cdc-integration.md`, `dbt-transformations.md`

### 3. Dev Memories

**Ne JAMAIS lire sans demande explicite de l'utilisateur.**
Repertoire : `.claude/dev-memories/`

---

## Reference rapide

### Architecture

- **Type** : Pipeline ELT industrialise pour donnees pharmacie
- **Flux** : MySQL RDS -> Kafka CDC -> Snowflake RAW -> dbt STG -> dbt MARTS
- **Sources** : 18 tables (4 CDC + 14 reference)
- **Transformations** : dbt 1.8 (SQL/Jinja2)
- **DWH** : Snowflake (RAW -> STAGING -> MARTS)
- **Streaming** : Debezium 2.7.3 + Kafka 7.5.0
- **Infra** : Docker Compose (6 services)
- **Monitoring** : Teams webhook + dbt source freshness

### Composants cles

| Module | Role |
|--------|------|
| `pipelines/daily_cdc_batch.py` | Consumer Kafka -> INSERT Snowflake RAW (4 tables CDC) |
| `pipelines/bulk_load.py` | MySQL SELECT -> Parquet -> COPY INTO RAW (18 tables) |
| `pipelines/diagnose_recover.py` | Diagnostic et recovery |
| `dbt/models/staging/stg_*.sql` | Dedup CDC + PII masking (18 modeles) |
| `dbt/models/marts/dim_*.sql` | 3 dimensions (pharmacie, produit, fournisseur) |
| `dbt/models/marts/fact_*.sql` | 8 faits (ventes, commandes, stock, ruptures...) |
| `dbt/models/marts/mart_kpi_*.sql` | KPIs metier (marge, ecoulement, ABC...) |
| `dbt/macros/pii_masking.sql` | Macros masquage PII (MD5) |
| `scripts/batch_loop.sh` | Orchestration principale (boucle 5-30 min) |
| `scripts/setup.sh` | Setup initial (Docker + DDL + Debezium) |

### Securite critique

- PII masquees par MD5 dans staging (noms, adresses, telephones)
- Requetes parametrees exclusivement dans les pipelines Python
- Pas d'interpolation de chaines dans les requetes SQL
- Credentials via `.env` (non versionne)
- Role Snowflake `MEDIcore_DBT_EXECUTOR` pour isolation

### Commandes essentielles

```bash
docker compose up -d                     # Demarrer tous les services
docker exec -it medicore_elt_batch bash  # Shell dans le conteneur
dbt run --select tag:staging             # Lancer staging
dbt run --select tag:marts               # Lancer marts
dbt test --select stg_*                  # Tests staging
dbt source freshness                     # Verifier fraicheur
python pipelines/bulk_load.py            # Bulk load complet
python pipelines/daily_cdc_batch.py      # Consumer CDC
```

### Conventions

- **Code** : Anglais
- **Commentaires/Docstrings** : Francais (Google-style)
- **Messages monitoring** : Francais
- **Commits** : Francais, atomiques, concis
- **Branches** : kebab-case (`feature/xxx`, `fix/xxx`)
- **SQL/dbt** : UPPERCASE pour mots-cles, snake_case pour colonnes

### Couches de donnees

| Couche | Schema | Materialisation | Description |
|--------|--------|-----------------|-------------|
| RAW | `RAW` | Tables | Copie brute MySQL + metadonnees CDC |
| STAGING | `STAGING` | Views/Incremental | Dedup CDC + PII masking + typage |
| MARTS | `MARTS` | Tables/Incremental | Dimensions + Faits + KPIs (star schema) |

### 4 Tables CDC

`COMMANDES` | `FACTURES` | `ORDERS` | `MODSTOCK`

### 14 Tables reference

`DAYBYDAY` | `EAN13` | `FOURNISSEURS` | `HISTORY` | `LOG` | `LPPR` | `OPERATEUR` | `PHARMACIE` | `PRODUITS` | `QUANTHEB` | `REMISE` | `STOCK` | `TRESORERIE` | `VENTEPRD`
