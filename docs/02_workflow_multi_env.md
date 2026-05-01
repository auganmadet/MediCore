# Workflow Multi-Environnement MediCore

## Table des matières

1. [Objectif](#objectif)
2. [Environnements](#environnements)
3. [Schéma global](#schéma-global)
4. [Workflow 1 — Données CDC en production](#workflow-1--données-cdc-en-production)
5. [Initialiser MEDICORE_DEV (clone de production)](#initialiser-medicore_dev-clone-de-production) — prérequis Workflow 2
   - [Quand cloner ?](#quand-cloner-)
   - [Procédure](#procédure)
   - [Vérification](#vérification)
   - [Utilisation](#utilisation)
6. [Initialiser MEDICORE_TEST (CI)](#initialiser-medicore_test-ci) — prérequis Workflow 2 (CI)
   - [Quand créer ?](#quand-créer-)
   - [Procédure](#procédure-1)
   - [Vérification](#vérification-1)
7. [Workflow 2 — Développement d'un nouveau modèle dbt](#workflow-2--développement-dun-nouveau-modèle-dbt)
8. [Workflow 3 — Bulk load des tables référence](#workflow-3--bulk-load-des-tables-référence)
9. [AUDIT — Lineage opérationnel](#audit--lineage-opérationnel)
   - [Tables](#tables)
   - [Rétention](#rétention)
   - [Consultation](#consultation)
   - [Tests par environnement](#tests-par-environnement)
10. [SNAPSHOTS — Historisation SCD2 des dimensions](#snapshots--historisation-scd2-des-dimensions)
    - [Tables](#tables-1)
    - [Fonctionnement](#fonctionnement)
    - [Exemple de consultation](#exemple-de-consultation)
    - [Flux dans batch_loop.sh](#flux-dans-batch_loopsh)
11. [GitHub Secrets (CI)](#github-secrets-ci)
    - [Configuration](#configuration-2)
12. [Branch protection (main)](#branch-protection-main)
    - [Configuration](#configuration-3)
    - [Flux résultant](#flux-résultant)
13. [Règle d'or](#règle-dor)

---

## Objectif

Isoler les environnements de développement, de test et de production pour garantir
que les modifications de code ne perturbent jamais les dashboards Metabase ni les
données de production. Chaque environnement a sa propre database Snowflake, ses
propres données et son propre usage.

[↑ Retour au sommaire](#table-des-matières)

---

## Environnements

  ┌───────────────┬─────────────────────────────────────────────────────────────────────────┐
  │ Environnement │ Description                                                             │
  ├───────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_DEV  │ Bac à sable du développeur. Données clonées ou manuelles. Permet de     │
  │               │ tester des modifications de modèles dbt, de scripts Python ou de SQL    │
  │               │ sans aucun risque. Aucun service externe ne lit cet environnement.      │
  ├───────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_TEST │ Environnement d'intégration continue (CI). Alimenté par des seeds dbt   │
  │               │ (données de test reproductibles). GitHub Actions y exécute dbt run +    │
  │               │ dbt test à chaque git push. Valide que le code fonctionne avant merge.  │
  ├───────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_PROD │ Production. Alimenté par les données réelles (CDC Kafka + bulk load     │
  │               │ MySQL). batch_loop.sh y exécute dbt en boucle (30 min). Metabase lit    │
  │               │ exclusivement cet environnement. Les utilisateurs finaux ne voient      │
  │               │ que les données de production.                                          │
  └───────────────┴─────────────────────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Schéma global

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              SOURCES EXTERNES                                       │
│                                                                                     │
│  ┌────────────┐    ┌──────────┐    ┌──────────┐                                     │
│  │ MySQL RDS  │──▶│ Debezium │───▶│  Kafka   │ ───── Workflow 1 : CDC (4 tables)   │
│  │ (WinStat)  │    └──────────┘    └──────────┘       temps réel, chaque boucle     │
│  │            │                                                                     │
│  │ 18 tables  │────────────────────────────────────── Workflow 3 : bulk load        │
│  └────────────┘                                       14 tables ref. (23h FR)       │
└─────────────────────────────────────────────────────────────────────────────────────┘
         │                            │                            │
         ▼                            ▼                            ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────────────────────────┐
│    MEDICORE_DEV      │  │    MEDICORE_TEST     │  │                MEDICORE_PROD                     │
│   (développement)    │  │      (CI/CD)         │  │                (production)                      │
│                      │  │                      │  │                                                  │
│ Qui : développeur    │  │ Qui : GitHub CI      │  │  ┌────────────────────────────────────────────┐  │
│ Quand : local        │  │ Quand : git push     │  │  │       batch_loop.sh (boucle 30 min)        │  │
│                      │  │                      │  │  │                                            │  │
│                      │  │                      │  │  │  WORKFLOW 1 (30 min) │ WORKFLOW 3 (23h FR) │  │
│ ┌─────────────────┐  │  │ ┌─────────────────┐  │  │  │                      │                     │  │
│ │ RAW             │  │  │ │ RAW             │  │  │  │  batch_loop.sh       │ batch_loop.sh       │  │
│ │ (clone)         │  │  │ │ (seeds dbt)     │  │  │  │       │              │      │              │  │
│ └────────┬────────┘  │  │ └────────┬────────┘  │  │  │       ▼              │      ▼              │  │
│          │           │  │          │           │  │  │  daily_cdc_batch.py  │ bulk_load.py        │  │
│          ▼           │  │          ▼           │  │  │       │              │      │              │  │
│ ┌─────────────────┐  │  │ ┌─────────────────┐  │  │  │  Kafka ──▶ RAW      │ MySQL ──▶ RAW       │  │
│ │ STAGING         │  │  │ │ STAGING         │  │  │  │  (4 tables CDC)      │ (14 tables ref.)    │  │
│ │ --target dev    │  │  │ │ --target test   │  │  │  │       │              │      │              │  │
│ │ (dédup + PII)   │  │  │ │ (dédup + PII)   │  │  │  │       └──────────┬───┘──────┘              │  │
│ └────────┬────────┘  │  │ └────────┬────────┘  │  │  │                  │                         │  │
│          │           │  │          │           │  │  │                  ▼                         │  │
│          ▼           │  │          ▼           │  │  │ ┌─────────────────────────────────────┐    │  │
│ ┌─────────────────┐  │  │ ┌─────────────────┐  │  │  │ │ STAGING                             │    │  │
│ │ MARTS           │  │  │ │ MARTS           │  │  │  │ │ dbt run --target prod               │    │  │
│ │ --target dev    │  │  │ │ --target test   │  │  │  │ │ (dédup CDC + PII masking)           │    │  │
│ │ (dims+facts+KPI)│  │  │ │ (dims+facts+KPI)│  │  │  │ └────────────────┬────────────────────┘    │  │
│ └─────────────────┘  │  │ │ + dbt test      │  │  │  │                  │                         │  │
│                      │  │ └─────────────────┘  │  │  │                  ▼                         │  │
│                      │  │                      │  │  │ ┌─────────────────────────────────────┐    │  │
│                      │  │                      │  │  │ │ MARTS                               │    │  │
│                      │  │                      │  │  │ │ dbt run --target prod               │────┼──┼──▶ Metabase
│                      │  │                      │  │  │ │ (dims + facts + KPIs)               │    │  │
│                      │  │                      │  │  │ └────────────────┬────────────────────┘    │  │
│                      │  │                      │  │  │                  │                         │  │
│                      │  │                      │  │  │                  ▼                         │  │
│                      │  │                      │  │  │ ┌─────────────────────────────────────┐    │  │
│                      │  │                      │  │  │ │ dbt test + freshness                │    │  │
│                      │  │                      │  │  │ │ → Alertes Teams si KO               │    │  │
│                      │  │                      │  │  │ └─────────────────────────────────────┘    │  │
│                      │  │                      │  │  │                                            │  │
│                      │  │                      │  │  └────────────────────────────────────────────┘  │
│                      │  │                      │  │                                                  │
│                      │  │                      │  │  ┌────────────────────────────────────────────┐  │
│                      │  │                      │  │  │ AUDIT + SNAPSHOTS (monitoring + SCD2)      │  │
│                      │  │                      │  │  └────────────────────────────────────────────┘  │
└──────────────────────┘  └──────────────────────┘  └──────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      WORKFLOW 2 — DÉVELOPPEMENT                                     │
│                                                                                     │
│  1. Modifier le code       2. git push              3. merge sur main               │
│     (modèle dbt, script)      │                        │                            │
│     │                         ▼                        ▼                            │
│     ▼                   ┌──────────────┐         ┌──────────────┐                   │
│  dbt run --target dev   │ GitHub CI    │         │ batch_loop.sh│                   │
│  sur MEDICORE_DEV       │ run + test   │         │ --target prod│                   │
│     │                   │      │       │         │      │       │                   │
│     ▼                   │      ▼       │         │      ▼       │                   │
│  Vérifier localement    │ ✅ → merge   │         │ MEDICORE_PROD│                   │
│  (aucun impact prod)    │ ❌ → corriger│         │ → Metabase   │                   │
│                         └──────────────┘         └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---

## Workflow 1 — Données CDC en production

Flux automatique, sans intervention humaine. Se déclenche quand une donnée est
modifiée ou créée dans MySQL RDS sur les 4 tables CDC (COMMANDES, FACTURES, ORDERS, MODSTOCK).

```
1. MySQL RDS             Un pharmacien saisit une vente dans WinStat
       │
       ▼
2. Debezium              Capture le changement via le binlog MySQL
       │
       ▼
3. Kafka                 Event CDC publié sur le topic winstat.winstat.COMMANDES
       │
       ▼
4. batch_loop.sh         Orchestre la boucle (toutes les 30 min) :
       │
       ├──▶ daily_cdc_batch.py
       │    Consumer lit les events Kafka, INSERT dans
       │    MEDICORE_PROD.RAW.RAW_COMMANDES
       │
       ├──▶ dbt run --target prod --select tag:staging
       │    → MEDICORE_PROD.STAGING (dédup CDC + PII masking)
       │
       ├──▶ dbt run --target prod --select tag:marts
       │    → MEDICORE_PROD.MARTS (dims + facts + KPIs)
       │
       ├──▶ dbt test --target prod
       │    → Validation des données
       │
       ├──▶ dbt source freshness --target prod
       │    → Alerte Teams si données trop anciennes
       │
       ▼
5. Metabase              Lit MEDICORE_PROD.MARTS → dashboards mis à jour
```

> **Seul MEDICORE_PROD est concerné.** DEV et TEST ne reçoivent jamais de données CDC.

[↑ Retour au sommaire](#table-des-matières)

---

## Initialiser MEDICORE_DEV (clone de production)

> **Prérequis du Workflow 2** — L'environnement MEDICORE_DEV doit exister avant
> de pouvoir développer avec `dbt run --target dev`. Cette section explique
> comment le créer et le maintenir à jour.

Le schéma RAW de l'environnement de développement est un **clone Snowflake** de la production.
Snowflake utilise le zero-copy cloning : pas de duplication physique des données, uniquement
des pointeurs. Le clone est instantané et ne coûte aucun crédit (sauf si les données sont modifiées).

### Quand cloner ?

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Situation                           │ Action                                                   │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Première mise en place de DEV       │ Cloner la prod                                           │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Données dev obsolètes (> 1 semaine) │ Re-cloner pour rafraîchir                                │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Après un gros changement de schéma  │ Re-cloner pour repartir d'une base propre                │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Développement en cours              │ Ne pas cloner (perte des modifications locales)          │
  └─────────────────────────────────────┴──────────────────────────────────────────────────────────┘

### Procédure

```sql
-- Connexion Snowflake avec un rôle ayant les droits CREATE DATABASE
USE ROLE ACCOUNTADMIN;  -- ou SYSADMIN selon votre configuration

-- 1. Supprimer l'ancienne base dev (si elle existe)
DROP DATABASE IF EXISTS MEDICORE_DEV;

-- 2. Cloner la prod (instantané, zero-copy)
CREATE DATABASE MEDICORE_DEV CLONE MEDICORE_PROD;

-- 3. Donner les droits au rôle dbt
GRANT ALL ON DATABASE MEDICORE_DEV TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_DEV TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT ALL ON ALL TABLES IN SCHEMA MEDICORE_DEV.RAW TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT ALL ON ALL TABLES IN SCHEMA MEDICORE_DEV.STAGING TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT ALL ON ALL TABLES IN SCHEMA MEDICORE_DEV.MARTS TO ROLE MEDICORE_DBT_EXECUTOR;
```

### Vérification

```sql
-- Vérifier que le clone contient les données
USE DATABASE MEDICORE_DEV;
SELECT 'RAW' AS schema, COUNT(*) AS nb_tables
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'RAW'
UNION ALL
SELECT 'STAGING', COUNT(*)
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'STAGING'
UNION ALL
SELECT 'MARTS', COUNT(*)
FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'MARTS';
```

Résultat attendu : mêmes nombres de tables que MEDICORE_PROD.

### Utilisation

```bash
# Lancer dbt sur l'environnement dev
dbt run --target dev      # écrit dans MEDICORE_DEV
dbt test --target dev     # teste sur MEDICORE_DEV
```

> **Important** : le clone est un snapshot à un instant T. Les nouvelles données CDC/bulk load
> arrivent uniquement dans MEDICORE_PROD. Pour rafraîchir dev, re-cloner.

> **Coût** : le clone lui-même est gratuit (zero-copy). Snowflake ne facture du stockage
> supplémentaire que si les données du clone sont **modifiées** (dbt run crée de nouvelles
> versions des tables STAGING et MARTS).

[↑ Retour au sommaire](#table-des-matières)

---

## Initialiser MEDICORE_TEST (CI)

> **Prérequis du Workflow 2 (CI)** — L'environnement MEDICORE_TEST doit exister pour que
> GitHub Actions puisse exécuter `dbt seed + run + test` lors d'un `git push`.

Contrairement à MEDICORE_DEV (clone de prod), MEDICORE_TEST est créée **vide** par
`DDL_WH.sql` avec uniquement le schéma RAW. Les schémas STAGING et MARTS sont ensuite
créés **automatiquement par dbt** lors du premier `dbt run --target test` en CI.
Les données sont injectées à chaque run CI via `dbt seed --full-refresh`
(fixtures reproductibles dans `dbt/seeds/`). Cela garantit des tests déterministes,
indépendants de l'état de la production.

### Quand créer ?

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Situation                           │ Action                                                   │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Première mise en place du projet    │ Exécuter DDL_WH.sql (crée tout)                          │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Database supprimée accidentellement │ Re-exécuter les commandes ci-dessous                     │
  └─────────────────────────────────────┴──────────────────────────────────────────────────────────┘

> En fonctionnement normal, MEDICORE_TEST n'a **jamais besoin d'être recréée**.
> La CI fait `dbt seed --full-refresh` à chaque run, ce qui recrée les données à partir des seeds.

### Procédure

```sql
-- Connexion Snowflake avec un rôle admin
USE ROLE ACCOUNTADMIN;

-- 1. Créer la database et le schéma RAW
CREATE DATABASE IF NOT EXISTS MEDICORE_TEST;
CREATE SCHEMA IF NOT EXISTS MEDICORE_TEST.RAW;

-- 2. Créer le rôle dédié à la CI
CREATE ROLE IF NOT EXISTS MEDICORE_TEST_EXECUTOR;
GRANT ALL ON DATABASE MEDICORE_TEST TO ROLE MEDICORE_TEST_EXECUTOR;
GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_TEST TO ROLE MEDICORE_TEST_EXECUTOR;
GRANT USAGE ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_TEST_EXECUTOR;

-- 3. Hiérarchie : DBT_EXECUTOR hérite du rôle TEST
GRANT ROLE MEDICORE_TEST_EXECUTOR TO ROLE MEDICORE_DBT_EXECUTOR;
```

> Ces commandes sont extraites de `scripts/DDL_WH.sql` (sections 3c et 13).
> Si le projet est initialisé via `DDL_WH.sql`, cette étape est déjà faite.

### Vérification

```sql
-- Vérifier que la database existe et que le rôle a les droits
USE ROLE MEDICORE_TEST_EXECUTOR;
USE DATABASE MEDICORE_TEST;
SHOW SCHEMAS IN DATABASE MEDICORE_TEST;
-- Attendu : RAW (initial), puis STAGING et MARTS après le premier dbt run en CI
```

> **Différence avec MEDICORE_DEV** : DEV est un clone complet de prod (données incluses).
> TEST est créée vide (seul RAW existe au départ) — STAGING et MARTS sont créés par dbt,
> et les données viennent des seeds dbt, injectées par la CI à chaque `git push`.

[↑ Retour au sommaire](#table-des-matières)

---

## Workflow 2 — Développement d'un nouveau modèle dbt

Flux manuel, déclenché par le développeur quand il modifie un modèle dbt,
un script Python ou toute autre partie du code.

```
1. Modifier le code
   │  Exemple : ajouter une colonne dans mart_kpi_marge.sql
   │
   ▼
2. dbt run --target dev
   │  Écrit dans MEDICORE_DEV.STAGING / MEDICORE_DEV.MARTS
   │  ❌ N'écrit PAS dans PROD
   │  Les dashboards Metabase ne sont pas impactés
   │
   ▼
3. Vérifier les résultats
   │  Requêtes SQL sur MEDICORE_DEV pour valider
   │  dbt test --target dev pour vérifier les contraintes
   │
   ▼
4. git add + git commit + git push
   │  Le code part sur GitHub (branche feature)
   │
   ▼
5. GitHub Actions (CI) — automatique
   │
   ├──▶ dbt run --target test
   │    → Exécute sur MEDICORE_TEST avec des seeds/fixtures
   │
   ├──▶ dbt test --target test
   │    → Valide not_null, unique, relationships, accepted_values
   │
   ├──▶ flake8 (lint Python)
   ├──▶ shellcheck (lint bash)
   └──▶ docker build (compilation Docker)
   │
   ▼
6. Tous les tests passent ?
   │
   ├── ✅ OUI → Pull Request → Review → Merge sur main
   │              │
   │              ▼
   │         batch_loop.sh exécute dbt run --target prod
   │         → MEDICORE_PROD mis à jour avec le nouveau code
   │         → Metabase reflète les changements
   │
   └── ❌ NON → Corriger → Retour à l'étape 1
```

> **MEDICORE_DEV** sert au développeur pour itérer rapidement.
> **MEDICORE_TEST** sert à la CI pour valider automatiquement.
> **MEDICORE_PROD** n'est mis à jour qu'après merge sur main.

[↑ Retour au sommaire](#table-des-matières)

---

## Workflow 3 — Bulk load des tables référence

Flux automatique quotidien (23h FR / 21h UTC) pour les 14 tables référence, avec pattern CLONE+SWAP.
Concerne uniquement MEDICORE_PROD.

```
1. batch_loop.sh         Détecte l'heure 23h FR (21h UTC), orchestre :
       │
       ├──▶ bulk_load.py
       │    Pour chaque table référence :
       │    MySQL SELECT → Parquet → PUT @stage → COPY INTO
       │    → MEDICORE_PROD.RAW.RAW_FOURNISSEURS, RAW_PRODUITS, etc.
       │
       ├──▶ dbt run --target prod --select tag:staging
       │    → MEDICORE_PROD.STAGING
       │
       ├──▶ dbt run --target prod --select tag:marts
       │    → MEDICORE_PROD.MARTS
       │
       └──▶ dbt test + freshness
            → Alertes Teams si KO
       │
       ▼
2. Metabase              Données référence à jour dans les dashboards
```

[↑ Retour au sommaire](#table-des-matières)

---

## AUDIT — Lineage opérationnel

Le schéma `MEDICORE.AUDIT` trace l'exécution du pipeline. Il est alimenté
automatiquement par `batch_loop.sh` et les scripts Python via `pipelines/utils/audit.py`.

**Uniquement en PROD** — DEV et TEST n'écrivent pas dans AUDIT.

### Tables

  ┌──────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │ Table                    │ Contenu                                                          │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ PIPELINE_RUNS            │ Une ligne par exécution de `batch_loop.sh` (RUN_ID, début, fin,  │
  │                          │ statut, nb erreurs)                                              │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ PIPELINE_STEP_RUNS       │ Détail par phase : CDC, staging, marts, tests, freshness,        │
  │                          │ snapshot (durée, statut, message d'erreur)                       │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ DBT_MODEL_RUNS           │ Résultat par modèle dbt (nom, durée, rows affected, statut)      │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ CDC_LAG_METRICS          │ Lag Kafka par topic (nb events en retard, timestamp)             │
  └──────────────────────────┴──────────────────────────────────────────────────────────────────┘

### Rétention

Les données AUDIT sont conservées 90 jours (nettoyage automatique dans `batch_loop.sh`).

### Consultation

```sql
-- Dernières exécutions
SELECT * FROM MEDICORE_PROD.AUDIT.PIPELINE_RUNS ORDER BY RUN_START DESC LIMIT 10;

-- Phases en erreur
SELECT * FROM MEDICORE_PROD.AUDIT.PIPELINE_STEP_RUNS WHERE STATUS = 'FAILED' ORDER BY STEP_START DESC;

-- Lag Kafka
SELECT * FROM MEDICORE_PROD.AUDIT.CDC_LAG_METRICS ORDER BY CREATED_AT DESC LIMIT 10;
```

### Tests par environnement

  ┌─────────────────┬─────────────────────────────────────────────────────────────────────────┐
  │ Environnement   │ Comment les tables/vues AUDIT sont testées                              │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_PROD   │ `batch_loop.sh` alimente les tables AUDIT à chaque boucle (30 min).     │
  │                 │ `dbt run --target prod` crée les vues AUDIT. Les données sont réelles.  │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_DEV    │ Tables AUDIT présentes (clone de PROD). `dbt run --target dev` crée     │
  │                 │ les vues. Testable manuellement.                                        │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ MEDICORE_TEST   │ Tables AUDIT **absentes** (créées par DDL, pas par dbt seed).           │
  │                 │ Les vues AUDIT sont **exclues** du `dbt run` en CI.                     │
  │                 │ `dbt parse` valide la syntaxe SQL des vues (compilation OK).            │
  └─────────────────┴─────────────────────────────────────────────────────────────────────────┘

> Les tables AUDIT (PIPELINE_RUNS, PIPELINE_STEP_RUNS, DBT_MODEL_RUNS, CDC_LAG_METRICS)
> sont créées par `DDL_TABLES.sql` et alimentées par les pipelines Python (`audit.py`,
> `kafka_lag.py`). Elles n'ont pas de seed dbt car les données sont générées au runtime.
> Les vues AUDIT sont de simples agrégations — le risque de bug est faible.

[↑ Retour au sommaire](#table-des-matières)

---

## SNAPSHOTS — Historisation SCD2 des dimensions

Le schéma `MEDICORE.SNAPSHOTS` capture l'historique des changements sur les
tables de dimension (SCD Type 2). Exécuté par `dbt snapshot --target prod`
dans chaque boucle de `batch_loop.sh`.

**Uniquement en PROD** — DEV et TEST n'exécutent pas les snapshots.

### Tables

  ┌──────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │ Snapshot                 │ Colonnes surveillées                                             │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ snap_pharmacie           │ PHA_NOM, PHA_GERS, PHA_DATE_INSTAL_WP                            │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ snap_produit             │ PRD_NOM, PRD_EAN13, FOU_ID, PRD_STOCK                            │
  ├──────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ snap_fournisseur         │ FOU_NOM, FOU_ADRESSE, FOU_VILLE, FOU_TYPE                        │
  └──────────────────────────┴──────────────────────────────────────────────────────────────────┘

### Fonctionnement

- **Stratégie** : `check` — dbt compare les colonnes surveillées à chaque exécution
- **Si un changement est détecté** : l'ancienne ligne reçoit un `dbt_valid_to` (date de fin), une nouvelle ligne est insérée avec `dbt_valid_from` (date de début) et `dbt_valid_to = NULL` (ligne courante)
- **Source** : les snapshots lisent depuis `{{ ref('stg_xxx') }}` (staging), jamais depuis RAW
- **Schéma cible** : `SNAPSHOTS` (séparé de STAGING et MARTS)

### Exemple de consultation

```sql
-- Historique des changements de nom d'une pharmacie
SELECT PHA_ID, PHA_NOM, dbt_valid_from, dbt_valid_to
FROM MEDICORE.SNAPSHOTS.SNAP_PHARMACIE
WHERE PHA_ID = 123
ORDER BY dbt_valid_from;

-- Toutes les modifications détectées aujourd'hui
SELECT *
FROM MEDICORE.SNAPSHOTS.SNAP_PRODUIT
WHERE dbt_valid_from::date = CURRENT_DATE();
```

### Flux dans batch_loop.sh

```
batch_loop.sh (chaque boucle 30 min)
    │
    ├── daily_cdc_batch.py → RAW
    ├── dbt run --select tag:staging → STAGING
    ├── dbt run --select tag:marts → MARTS
    ├── dbt test → validation
    ├── dbt snapshot → SNAPSHOTS (historisation SCD2)
    ├── dbt source freshness → alertes
    └── audit.py → AUDIT (lineage)
```

[↑ Retour au sommaire](#table-des-matières)

---

## GitHub Secrets (CI)

Le job `integration-dbt` de la CI a besoin de se connecter à Snowflake (MEDICORE_TEST)
pour exécuter `dbt seed + run + test`. Les credentials sont stockés dans GitHub Secrets
(chiffrés, invisibles après saisie).

### Configuration

1. Aller sur `https://github.com/auganmadet/MediCore/settings/secrets/actions`
2. Créer les secrets suivants :

  ┌──────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Nom du secret            │ Description                                              │
  ├──────────────────────────┼──────────────────────────────────────────────────────────┤
  │ SNOWFLAKE_ACCOUNT        │ Identifiant du compte Snowflake (format org-account)     │
  ├──────────────────────────┼──────────────────────────────────────────────────────────┤
  │ SNOWFLAKE_USER           │ Utilisateur Snowflake pour la CI                         │
  ├──────────────────────────┼──────────────────────────────────────────────────────────┤
  │ SNOWFLAKE_PASSWORD       │ Mot de passe de l'utilisateur CI                         │
  ├──────────────────────────┼──────────────────────────────────────────────────────────┤
  │ SNOWFLAKE_WAREHOUSE_NAME │ Warehouse Snowflake (ex: MEDICORE_WH)                    │
  ├──────────────────────────┼──────────────────────────────────────────────────────────┤
  │ SNOWFLAKE_DBT_ROLE_NAME  │ Rôle dbt (ex: MEDICORE_TEST_EXECUTOR ou DBT_EXECUTOR)    │
  └──────────────────────────┴──────────────────────────────────────────────────────────┘

> Ne jamais documenter les **valeurs** des secrets — uniquement les noms et descriptions.
> Les valeurs sont dans `.env` (non versionné) et GitHub Secrets (chiffrés).

[↑ Retour au sommaire](#table-des-matières)

---

## Branch protection (main)

Empêche que du code non testé arrive en production. Sans protection, un `git push`
direct sur `main` déclenche `batch_loop.sh` → dbt run sur MEDICORE_PROD → dashboards
Metabase potentiellement cassés.

### Configuration

1. Aller sur `https://github.com/auganmadet/MediCore/settings/branches`
2. Créer une règle pour la branche `main` :

  ┌──────────────────────────────────────────────┬──────────────┬──────────────────────────────────┐
  │ Option                                       │ Cocher       │ Effet                            │
  ├──────────────────────────────────────────────┼──────────────┼──────────────────────────────────┤
  │ Require a pull request before merging        │ Oui          │ Pas de push direct sur main      │
  ├──────────────────────────────────────────────┼──────────────┼──────────────────────────────────┤
  │ Require status checks to pass before merging │ Oui          │ CI verte obligatoire avant merge │
  ├──────────────────────────────────────────────┼──────────────┼──────────────────────────────────┤
  │ Status checks requis                         │ lint-python  │ Les 6 jobs CI doivent passer     │
  │                                              │ test-python  │                                  │
  │                                              │ validate-dbt │                                  │
  │                                              │ integration- │                                  │
  │                                              │ dbt          │                                  │
  │                                              │ build-docker │                                  │
  │                                              │ shellcheck   │                                  │
  ├──────────────────────────────────────────────┼──────────────┼──────────────────────────────────┤
  │ Do not allow bypassing the above settings    │ Optionnel    │ Même l'admin passe par une PR    │
  └──────────────────────────────────────────────┴──────────────┴──────────────────────────────────┘

### Flux résultant

```
Développeur :
  1. git checkout -b feature/xxx
  2. Modifier le code
  3. dbt run --target dev (vérification locale)
  4. git push origin feature/xxx
  5. GitHub Actions : 6 jobs CI (lint + test + dbt + build + shell)
  6. Créer Pull Request
  7. CI verte → Review → Merge sur main
  8. batch_loop.sh exécute dbt run --target prod → Metabase mis à jour
```

> Sans branch protection, l'étape 6-7 est sautée — le code arrive directement en prod.

[↑ Retour au sommaire](#table-des-matières)

---

## Règle d'or

```
DEV  = je casse, je teste, je recommence  → aucun impact
TEST = la CI valide automatiquement       → aucun impact
PROD = seul batch_loop.sh écrit ici       → Metabase toujours stable
```

[↑ Retour au sommaire](#table-des-matières)

---

## Voir aussi

- [Architecture](01_ARCHITECTURE.md) — vue d'ensemble des composants et flux de données
- [Opérations](03_operations.md) — exploitation quotidienne et monitoring
- [Rotation des credentials](09_rotation_credentials.md) — rotation trimestrielle (lié aux GitHub Secrets)
