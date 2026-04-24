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
- **DWH** : Snowflake MEDICORE_PROD (RAW -> STAGING -> MARTS -> AUDIT -> SNAPSHOTS)
- **Multi-env** : MEDICORE_DEV (clone), MEDICORE_TEST (seeds CI)
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
  │ `dbt/models/marts/mart_kpi_*.sql` │ 21 KPIs métier (marge, écoulement, ABC, stock...)     │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `dbt/macros/pii_masking.sql`      │ Macros masquage PII (MD5)                             │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `scripts/batch_loop.sh`           │ Orchestration principale (boucle 5-30 min)            │
  ├───────────────────────────────────┼───────────────────────────────────────────────────────┤
  │ `scripts/setup.sh`                │ Setup initial (Docker + DDL + Debezium)               │
  └───────────────────────────────────┴───────────────────────────────────────────────────────┘

### Metabase BI & Embedding

- **Metabase v0.58.7** + PostgreSQL 16, accès `http://localhost:3000`
- 16 dashboards (D1-D16), 98 cartes, embedding signé (JWT) pour les pharmaciens
- **Siège** (IT, Marketing, RH, Achats) : accès direct Metabase, filtrage par collections
- **Pharmaciens** : dashboards via iframes (signed embedding), filtre pharmacie verrouillé par JWT
- **Mini-app test** : `embed_app/` (Flask, port 5000) — simule l'intégration Mediprix
- **Surveillance à 4 niveaux** (depuis 2026-04-23) : pre-night (20h30) → post-CDC (~21h35) → post-ref_reload bloquant (~23h16) → pipeline_maintenance (~23h47)
- **Pre-night healthcheck** : `scripts/pre_night_healthcheck.py --fix` (14 checks H1-H7 + N2-N8, corrections auto)
- **Maintenance post-exécution** : `scripts/pipeline_maintenance.py --fix-safe` (4 phases : CDC, Bulk, dbt, Metabase ; enchaîne après dbt post-reload)
- **Orchestrateur Metabase** : `scripts/metabase_maintenance.py` (P1-P10, appelé par pipeline_maintenance)
- **Provisionnement pharmacies** : `scripts/provision_rls.py` (groupe + collection + permissions, détection auto)
- **10 problèmes identifiés** (P1-P10) : voir `docs/15_metabase_checklist_depannage.md`
- **Guide embedding Mediprix** : voir `docs/14_embedding_metabase.md`
- **Bilan RLS et options** : voir `docs/13_rls_bilan_et_options.md`
- **Maintenance pipeline complète** : voir `docs/16_pipeline_maintenance.md` (architecture 4 niveaux : pre-night + post-checks inline + pipeline_maintenance)
- **Optimisation coût Snowflake L1+L5** : voir `docs/plans/2026-04-22_optimisation_cost_snowflake.md` (incremental merge + skip dimanche, gain -391 EUR/mois)

### Sécurité critique

- PII masquées par MD5 dans staging : seule `FOU_ADRESSE` reste masquée
- Démasqué (raisons sociales/besoin métier) : `PHA_NOM`, `FOU_NOM`, `ORD_OPERATEUR`
- Requêtes paramétrées exclusivement dans les pipelines Python
- Pas d'interpolation de chaînes dans les requêtes SQL
- Credentials via `.env` (non versionné)
- Rôle Snowflake `MEDICORE_DBT_EXECUTOR` pour isolation (+ `MEDICORE_DEV_EXECUTOR`, `MEDICORE_TEST_EXECUTOR`)

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

`DAYBYDAY` | `EAN13` | `FOURNISSEURS` | `HISTORY` | `LOG` | `LPPR` | `MANQHISTORY` | `MEDIPRIX_FACTURES` | `PHARMACIE` | `PHARMACIES` | `PHARMACIES_ERREUR` | `PRODUITS` | `PRODUITS_NEGATIFS` | `STOCKHISTORY`
