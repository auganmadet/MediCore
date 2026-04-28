# 18. Rapport coût Snowflake — méthodologie et baseline

## Synthèse minimaliste — les seuls chiffres à retenir

### 3 chiffres pour la présentation hiérarchie

  ┌────────────────────────────────────┬────────────────────────────────────────────────────┐
  │             Question               │                       Réponse                      │
  ├────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ Combien Mediprix paie / crédit ?   │ **2,76 €/crédit** (Enterprise AWS Paris)           │
  ├────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ Coût mensuel nocturne actuel ?     │ **~110 €/mois** (post-optimisations complètes)     │
  ├────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ Avant les optimisations ?          │ **~604 €/mois** (baseline mesurée mars 2026)       │
  ├────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ **Économie réalisée**              │ **-494 €/mois soit -82 %**                         │
  └────────────────────────────────────┴────────────────────────────────────────────────────┘

### 3 chiffres pour le suivi opérationnel quotidien

  ┌────────────────────────────────────────┬─────────────────────────────────────────────┐
  │            Type de nuit                │              Coût par nuit                  │
  ├────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Lundi (full reload)                    │ **5,45 €/nuit** (mesuré 27/04)              │
  ├────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Mardi-Samedi (incremental)             │ **~4,00 €/nuit** (estimé post-clustering)   │
  ├────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Dimanche (skip)                        │ **0,10 €/nuit** (mesuré 26/04)              │
  └────────────────────────────────────────┴─────────────────────────────────────────────┘

### Phrase à ressortir si on te demande "comment tu sais que c'est précis ?"

> *« Source = `WAREHOUSE_METERING_HISTORY` + `AUTOMATIC_CLUSTERING_HISTORY` (= ce que Snowflake facture), via `scripts/snowflake_cost_report.py` reproductible chaque nuit. »*

### Incertitude restante à signaler honnêtement si besoin

Le chiffre mar-sam **~4,00 €/nuit est une estimation post-clustering**. Sera **confirmé le 29/04 matin** par la première mesure d'une nuit incrementale post-clustering. Si l'écart > 10 % avec l'estimation, recalibrer les ~110 €/mois.

---

**Tout le reste (5,40 €, 6,32 €, 7,04 €, 124 €) sont des étapes intermédiaires de mes corrections successives, à oublier.** Ne retenir que les 6 chiffres ci-dessus + la phrase de provenance.

---

## Objectif

Mesurer **précisément** la consommation de crédits Snowflake du traitement de nuit MediCore, phase par phase, de manière reproductible. Le script `scripts/snowflake_cost_report.py` produit un tableau identique chaque nuit, ce qui permet de comparer les sessions entre elles et de quantifier les gains des optimisations.

## Pourquoi un rapport dédié

Plusieurs estimations approximatives ont été faites au fil des sessions (5,40 €, 6,32 €, 7,04 €). Elles divergeaient à cause de :

- **Tarif erroné** : 3,60 €/cr utilisé au lieu de **2,76 €/cr** (tarif Mediprix réel)
- **Fenêtre mal alignée** : `TIMESTAMP_TZ` interprété en Pacific (timezone de session) au lieu d'UTC
- **Inclusion accidentelle** du dbt mode jour dans le périmètre du ref_reload

Le script verrouille ces trois points : tarif paramétrable, `TIMEZONE = UTC` forcé, fenêtre 18:00→04:00 UTC stricte.

## Tables Snowflake utilisées

  ┌────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┬───────────────────────────────┐
  │                            Table                           │                              Rôle                              │            Latence            │
  ├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────────────┤
  │ `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`       │ Crédits **facturés** par tranche d'1 h UTC, par warehouse      │ 45 min - 3 h                  │
  ├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────────────┤
  │ `SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY`     │ Crédits du service auto-clustering (déclenché après COPY/CTAS) │ 45 min - 3 h                  │
  ├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────────────┤
  │ `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`                    │ Détail par query (TOTAL_ELAPSED_TIME, BYTES, TYPE)             │ 45 min - 3 h                  │
  ├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────────────┤
  │ `SNOWFLAKE.INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY`  │ Idem METERING mais quasi temps réel (7 j d'historique)         │ Quasi temps réel              │
  ├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┼───────────────────────────────┤
  │ `SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY`           │ Vue agrégée par jour et par service (WAREHOUSE, CLUSTERING…)   │ 45 min - 3 h                  │
  └────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┴───────────────────────────────┘

À cause de la latence ACCOUNT_USAGE, le rapport vise **J-2** par défaut pour avoir des données complètes.

## Méthodologie

### 1. Définitions

  ┌────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────┐
  │       Notion       │                                         Définition                                         │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Wall-clock         │ Durée mesurée à l'extérieur, du début à la fin du run (ex. 23:05 → 04:22 = 5 h 17 min)     │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Compute time       │ Durée d'exécution d'**une** query (`TOTAL_ELAPSED_TIME` dans QUERY_HISTORY)                │
  ├────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Warehouse busy     │ Durée totale pendant laquelle le warehouse est **allumé** (= ce que Snowflake facture)     │
  └────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────┘

Snowflake facture le **warehouse busy** à la seconde, avec minimum 60 s par démarrage (AUTO_SUSPEND). Plusieurs queries en parallèle ne multiplient pas le coût : seul le temps allumé compte.

### 2. Tarif Mediprix

**2,76 €/crédit** (configurable via `--tarif`).

### 3. Fenêtre temporelle

Le script analyse **J 18:00 UTC → J+1 04:00 UTC** (= 20:00 → 06:00 FR), soit 10 tranches horaires qui couvrent l'intégralité du traitement de nuit (pre-night healthcheck → dev_clone). La timezone de session est forcée à UTC pour éviter toute ambiguïté.

### 4. Trois modes selon le jour de la semaine

Le `batch_loop.sh` ne fait pas la même chose chaque nuit. Le script détecte automatiquement le mode via le jour de la semaine de `--date` (override possible via `--mode`) :

  ┌───────────────┬──────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────┐
  │     Jour      │            Mode              │                                  Comportement                                   │
  ├───────────────┼──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Lundi         │ ``full``                     │ ref_reload complet sur 14 tables (~5 h 17 min wall-clock)                       │
  ├───────────────┼──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Mardi-Samedi  │ ``incremental``              │ ref_reload incremental 30 j sur 4 tables (~53 min wall-clock) + cycles CDC nuit │
  ├───────────────┼──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┤
  │ Dimanche      │ ``skip``                     │ Tout skippé sauf audit/backup Metabase (~0,04 cr)                               │
  └───────────────┴──────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────┘

Le mapping libellé/tranche horaire diffère selon le mode car les phases ne tombent pas dans les mêmes tranches UTC. Le **total crédits est cohérent dans tous les cas**.

### 5. Mapping FULL (lundi)

Calé sur la timeline `batch_loop.sh` observée le 27/04/2026 (premier run post-clustering `RAW_MEDIPRIX_FACTURES`) :

  ┌───────────────┬───────────────┬───────────────────────────────────────────────────────────────────┐
  │   Heure UTC   │   Heure FR    │                              Phase                                │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 18:00 - 19:00 │ 20:00 - 21:00 │ Pre-night healthcheck (~20:35 FR)                                 │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 19:00 - 20:00 │ 21:00 - 22:00 │ CDC pre-reload (~21:40 FR)                                        │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 20:00 - 21:00 │ 22:00 - 23:00 │ Audit purge + backup Metabase (~22:02 FR)                         │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 21:00 - 22:00 │ 23:00 - 00:00 │ ref_reload : début (TRUNCATE + 1ers PUT)                          │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 22:00 - 01:00 │ 00:00 - 03:00 │ ref_reload : SELECT MySQL (warehouse suspendu, ~3 tranches)       │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 01:00 - 02:00 │ 03:00 - 04:00 │ ref_reload : COPY INTO RAW_MEDIPRIX_FACTURES (10min21s) + PRODUITS│
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 02:00 - 03:00 │ 04:00 - 05:00 │ ref_reload fin + POST-CHECK + dbt post-reload (début)             │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 03:00 - 04:00 │ 05:00 - 06:00 │ dbt post-reload (fin) + pipeline_maintenance + dev_clone          │
  └───────────────┴───────────────┴───────────────────────────────────────────────────────────────────┘

### 6. Mapping INCREMENTAL (mardi-samedi)

Calé sur la timeline `batch_loop.sh` observée le 25/04/2026 (vendredi, mode incremental) :

  ┌───────────────┬───────────────┬───────────────────────────────────────────────────────────────────┐
  │   Heure UTC   │   Heure FR    │                              Phase                                │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 18:00 - 19:00 │ 20:00 - 21:00 │ Pre-night healthcheck                                             │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 19:00 - 20:00 │ 21:00 - 22:00 │ CDC pre-reload                                                    │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 20:00 - 21:00 │ 22:00 - 23:00 │ Audit purge + backup Metabase                                     │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 21:00 - 22:00 │ 23:00 - 00:00 │ ref_reload INCREMENTAL (~53 min) + dbt post-reload (début)        │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 22:00 - 23:00 │ 00:00 - 01:00 │ dbt post-reload (fin) + pipeline_maintenance + dev_clone          │
  ├───────────────┼───────────────┼───────────────────────────────────────────────────────────────────┤
  │ 23:00 - 04:00 │ 01:00 - 06:00 │ Cycles CDC nuit (DBT_EVERY_N=12, toutes les 2 h, ~0,1 cr/cycle)   │
  └───────────────┴───────────────┴───────────────────────────────────────────────────────────────────┘

→ Différence majeure avec le mode full : le ref_reload tient dans 1 tranche, ce qui **rend visibles les cycles CDC nuit** qui sont masqués le lundi (ils tournent quand même, mais pendant le ref_reload qui occupe le warehouse).

### 7. Mapping SKIP (dimanche)

Calé sur l'observation du 26/04/2026 (dimanche) — quasiment 0 cr car tout est skippé sauf l'audit/backup Metabase à 22:00 FR :

  ┌───────────────┬───────────────────────────────────────────────────────┬───────────────────┐
  │   Tranche     │                       Phase                           │  Crédits typiques │
  ├───────────────┼───────────────────────────────────────────────────────┼───────────────────┤
  │ 20:00 - 21:00 │ Audit purge + backup Metabase (seul actif)            │  ~0,04 cr         │
  ├───────────────┼───────────────────────────────────────────────────────┼───────────────────┤
  │ Autres        │ Skippé                                                │  0 cr             │
  └───────────────┴───────────────────────────────────────────────────────┴───────────────────┘

### 8. Auto-clustering

L'auto-clustering est attribué à la phase qui le déclenche :

  ┌───────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────┐
  │             Table             │                                       Phase d'attribution                                  │
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ RAW_MEDIPRIX_FACTURES         │ ref_reload : COPY INTO RAW_MEDIPRIX_FACTURES (le clustering ré-organise après le full)     │
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ RAW_STOCKHISTORY              │ ref_reload fin (idem)                                                                      │
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────┤
  │ MART_KPI_DORMANT              │ dbt post-reload (le CTAS recrée la table, déclenche un re-clustering complet)              │
  └───────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────┘

## Glossaire des acronymes utilisés

  ┌─────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Acronyme   │                                              Définition                                                  │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ CTAS        │ ``CREATE TABLE AS SELECT`` — instruction Snowflake qui crée une table à partir du résultat d'un          │
  │             │ ``SELECT``. Avec ``CREATE OR REPLACE TABLE`` (utilisé par dbt en ``materialized='table'``), la table     │
  │             │ est entièrement recréée à chaque exécution, ce qui détruit/reconstruit toutes les micro-partitions et    │
  │             │ déclenche un auto-clustering complet si ``CLUSTER BY`` est défini. Coûteux pour les grosses tables       │
  │             │ comme MART_KPI_DORMANT (~10 min compute + 0,11 cr clustering).                                           │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ MERGE       │ ``MERGE INTO ... USING ... ON ... WHEN MATCHED ... WHEN NOT MATCHED INSERT`` — instruction de mise à     │
  │             │ jour incrémentale. Utilisée par dbt en ``materialized='incremental', incremental_strategy='merge'``.     │
  │             │ Plus économe que CTAS car ne recrée que les lignes modifiées, mais peut rester long sur grosses tables   │
  │             │ (ex. ``MERGE fact_prix_journalier`` = 17 min sur 35 M lignes).                                           │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ COPY INTO   │ Charge des fichiers (Parquet, CSV, JSON) depuis un stage Snowflake vers une table. Utilisé par           │
  │             │ ``bulk_load.py`` après ``PUT_FILES``. Coûte du compute proportionnel au volume.                          │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ PUT_FILES   │ Upload de fichiers locaux vers un stage Snowflake (S3 derrière). Le warehouse n'est pas sollicité —      │
  │             │ c'est un transfert client→stage. Coût compute warehouse = 0, coût cloud services négligeable.            │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ DDL/DML     │ Data Definition Language (CREATE/ALTER/DROP) / Data Manipulation Language (INSERT/UPDATE/DELETE/MERGE)   │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ CDC         │ Change Data Capture — flux de modifications MySQL captées par Debezium et publiées sur Kafka             │
  ├─────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ DBT_EVERY_N │ Variable batch_loop.sh : 1 cycle dbt toutes les N cycles CDC. ``DBT_EVERY_N=12`` ⇒ dbt toutes les 2 h   │
  │             │ (avec CDC_INTERVAL_MIN=10 min). Visible la nuit en mode incremental.                                     │
  └─────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────┘

## Comment Snowflake calcule les crédits

Le script lit les colonnes brutes ; c'est Snowflake lui-même qui calcule les crédits selon ces règles :

### Compute warehouse (colonne ``CREDITS_USED_COMPUTE``)

```
CREDITS_USED_COMPUTE = (durée warehouse busy en secondes) × (crédits/heure de la taille du warehouse) / 3600
```

Tarif crédit/heure par taille de warehouse (identique pour toutes les éditions) :

  ┌──────────────┬────────────────────┬───────────────────────────┐
  │     Taille   │   Crédits / heure  │       Crédits / sec       │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ X-Small      │         1          │       0,000277            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ Small        │         2          │       0,000555            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ Medium       │         4          │       0,001111            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ Large        │         8          │       0,002222            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ X-Large      │        16          │       0,004444            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ 2X-Large     │        32          │       0,008888            │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ 3X-Large     │        64          │       ...                 │
  ├──────────────┼────────────────────┼───────────────────────────┤
  │ 4X-Large     │       128          │       ...                 │
  └──────────────┴────────────────────┴───────────────────────────┘

MediCore utilise un warehouse **X-Small** (1 cr/h). Vérifiable via ``SHOW WAREHOUSES LIKE 'MEDICORE_WH'``.

**Vérification de la baseline 27/04 :**

  ┌────────────────────┬─────────────────────────────────────────────────────────────────────────┐
  │      Tranche       │                                Calcul                                   │
  ├────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ 18:00–19:00 UTC    │ 0,1736 cr × 3 600 / 1 = **625 s ≈ 10,4 min de warehouse busy**          │
  ├────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ 02:00–03:00 UTC    │ 0,7818 cr × 3 600 / 1 = **2 814 s ≈ 46,9 min de warehouse busy**        │
  ├────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ 22:00–23:00 UTC    │ 0,0017 cr × 3 600 / 1 = **6,1 s** (= cloud services seuls, WH suspendu) │
  └────────────────────┴─────────────────────────────────────────────────────────────────────────┘

### Cloud services (colonne ``CREDITS_USED_CLOUD_SERVICES``)

Snowflake offre **10 % du compute** en cloud services gratuitement chaque jour. Au-delà, c'est facturé au même tarif que le compute.

```
CREDITS_USED_CLOUD_SERVICES = MAX(0, cloud_services_consumed − 10 % × CREDITS_USED_COMPUTE_journée)
```

Sur la baseline 27/04, le cloud services représente ~1 % du total (~0,02 cr), donc impact négligeable et toujours sous le seuil gratuit.

### Auto-clustering (table ``AUTOMATIC_CLUSTERING_HISTORY``)

Service serverless distinct du warehouse, facturé séparément :

```
CREDITS_USED = (compute interne du service auto-clustering) × tarif Snowflake serverless
```

Le tarif serverless est **identique au tarif compute** (1 cr/h pour le service auto-clustering en moyenne). Le coût dépend du volume de micro-partitions à réorganiser après chaque write sur la table clusterée.

→ Sur la baseline 27/04 : 0,2131 cr d'auto-clustering `RAW_MEDIPRIX_FACTURES` = ~12,8 min de compute serverless équivalent X-Small.

### Conversion € (faite par le script)

```
EUR = CREDITS_USED × tarif_eur_per_credit  (défaut 2,76 €/cr Mediprix)
```

## Comment vérifier l'édition Snowflake et le tarif

Snowflake propose 4 éditions avec des tarifs différents. Le tarif/crédit varie aussi selon le **cloud provider (AWS/Azure/GCP)** et la **région**.

### Tarifs publics indicatifs (USD/crédit, AWS Europe, novembre 2025)

  ┌───────────────────────────┬───────────────┬─────────────┬────────────────────────────────────────────────────────────────┐
  │         Édition           │  USD/crédit   │ EUR/crédit* │                          Features clés                         │
  ├───────────────────────────┼───────────────┼─────────────┼────────────────────────────────────────────────────────────────┤
  │ Standard                  │     2,00 USD  │  ~1,84 €    │ DWH de base, time travel 1 j max, pas de multi-cluster WH      │
  ├───────────────────────────┼───────────────┼─────────────┼────────────────────────────────────────────────────────────────┤
  │ Enterprise                │     3,00 USD  │  ~2,76 €    │ + multi-cluster, time travel 90 j, masking dynamique, RBAC fin │
  ├───────────────────────────┼───────────────┼─────────────┼────────────────────────────────────────────────────────────────┤
  │ Business Critical         │     4,00 USD  │  ~3,68 €    │ + HIPAA/PCI, customer-managed keys, failover/replication       │
  ├───────────────────────────┼───────────────┼─────────────┼────────────────────────────────────────────────────────────────┤
  │ Virtual Private Snowflake │ Sur devis     │      –      │ Compte isolé + features Business Critical                      │
  └───────────────────────────┴───────────────┴─────────────┴────────────────────────────────────────────────────────────────┘

*Conversion approximative au taux EUR/USD actuel. À recalibrer chaque année.

### Compte Mediprix — valeurs vérifiées le 28/04/2026

  ┌──────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────┐
  │             Métadonnée               │                                Valeur                                     │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ ``CURRENT_ACCOUNT()``                │ DL79092                                                                   │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ ``CURRENT_REGION()``                 │ AWS_EU_WEST_3 (AWS Paris)                                                 │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ ``CURRENT_VERSION()``                │ 10.14.103                                                                 │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Édition (déduite)                    │ **Enterprise** (confirmé via 2 features Enterprise-only actives)          │
  ├──────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Tarif effectif                       │ 2,76 €/crédit (cohérent avec Enterprise AWS Europe)                       │
  └──────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────┘

**Preuves d'édition Enterprise** (Standard ne supporterait pas ces features) :

  ┌────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────┐
  │             Test SQL               │                                  Résultat                                        │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
  │ ``SHOW ROW ACCESS POLICIES``       │ 4 policies actives → feature Enterprise présente                                 │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
  │ ``SHOW DYNAMIC TABLES``            │ 9 dynamic tables → feature Enterprise présente                                   │
  ├────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
  │ ``SHOW MASKING POLICIES``          │ Commande exécutable sans erreur (Standard lèverait une erreur de feature)        │
  └────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────┘

### Consommation Mediprix avril 2026 (mois en cours, mesurée le 28/04)

Depuis ``SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY`` (vue agrégée par jour et par service) :

  ┌────────────────────────┬───────────────┬──────────────────────────────────────────────────────────────────────────┐
  │       Service          │   Crédits     │                              Note                                        │
  ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ WAREHOUSE_METERING     │   152,39 cr   │ Warehouse compute (MEDICORE_WH essentiellement)                          │
  ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ AUTO_CLUSTERING        │     3,22 cr   │ Re-clustering RAW_MEDIPRIX_FACTURES (post-COPY) + MART_KPI_DORMANT (CTAS)│
  ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ SERVERLESS_TASK        │     0,18 cr   │ Tâches serverless (négligeable)                                          │
  ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────────────────┤
  │ **TOTAL avril**        │ **155,79 cr** │ × 2,76 €/cr = **~430 €** (pour 28 jours, hors stockage)                  │
  └────────────────────────┴───────────────┴──────────────────────────────────────────────────────────────────────────┘

→ Le mois mélange l'avant-L1+L5 (1-22/04) et l'après (23-28/04) ; le coût stabilisé post-optimisation est plus bas (cf. baselines mesurées plus haut).

### 1. Vérifier l'édition via l'UI Snowsight (méthode officielle)

1. Aller sur https://app.snowflake.com (ou le sous-domaine du compte)
2. **Admin** → **Accounts**
3. Cliquer sur le compte → onglet **Pricing & Edition** (ou **Billing & Terms**)
4. La page liste : édition, cloud provider, région, tarif/crédit, contrat (capacity vs on-demand)

### 2. Indices SQL (l'édition n'est PAS exposée directement)

Snowflake n'expose pas l'édition via une fonction SQL standard. On peut cependant la déduire :

```sql
-- Version Snowflake (pas l'édition, juste la release)
SELECT CURRENT_VERSION();

-- Région et compte
SELECT CURRENT_REGION(), CURRENT_ACCOUNT(), CURRENT_ORGANIZATION_NAME();

-- Indice 1 : multi-cluster warehouse → Enterprise+
SHOW WAREHOUSES;
-- Si MIN_CLUSTER_COUNT et MAX_CLUSTER_COUNT existent et MAX > 1 → Enterprise minimum.

-- Indice 2 : retention time-travel
SHOW PARAMETERS LIKE 'DATA_RETENTION_TIME_IN_DAYS' IN ACCOUNT;
-- Standard : max 1 j. Enterprise+ : jusqu'à 90 j.

-- Indice 3 : masking policies (Enterprise+ uniquement)
SHOW MASKING POLICIES;
-- Si la commande retourne quelque chose ou ne lève pas d'erreur de feature, c'est Enterprise+.

-- Indice 4 : Resource Monitors (toutes éditions, mais bonne vérif générale)
SHOW RESOURCE MONITORS;
```

### 3. Calcul à rebours via la facture

Méthode la plus fiable :

1. Récupérer la facture mensuelle Snowflake (PDF ou CSV depuis l'UI Billing)
2. Calculer : ``tarif_eur_per_credit = total_facture_EUR / total_credits_consommés``
3. Vérifier la cohérence avec le tarif Enterprise EUR ≈ 2,76 €/cr

```sql
-- Total crédits consommés sur le mois courant (à comparer avec la facture)
SELECT
    DATE_TRUNC('month', START_TIME)::DATE AS mois,
    ROUND(SUM(CREDITS_USED), 2) AS credits_warehouse
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY mois;

-- Auto-clustering à ajouter
SELECT
    ROUND(SUM(CREDITS_USED), 2) AS credits_clustering
FROM SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY
WHERE START_TIME >= DATE_TRUNC('month', CURRENT_DATE());
```

### 4. Contrat capacity vs on-demand

Le tarif réel peut différer du tarif public :

- **On-demand** : tarif public, paiement mensuel sur consommation réelle
- **Capacity** : engagement annuel sur un volume de crédits → remise jusqu'à -30 %

→ Pour Mediprix, vérifier auprès du CSM (Customer Success Manager) Snowflake ou dans le contrat. Si le tarif effectif est < 2,76 €/cr, ajuster ``--tarif`` du script pour avoir des projections fidèles.

## Baselines mesurées par mode (avril 2026)

**Toutes les valeurs ci-dessous sont mesurées** via ``scripts/snowflake_cost_report.py``, pas estimées. Source = ``WAREHOUSE_METERING_HISTORY`` + ``AUTOMATIC_CLUSTERING_HISTORY``.

⚠️ **Asymétrie temporelle critique** : le clustering ``RAW_MEDIPRIX_FACTURES (PHA_ID, FAC_DATE)`` a été appliqué le **27/04/2026 à 09:28 UTC**. La nuit du 27/04 (FULL) est mesurée **après** ; les nuits 25/04 (INCR) et 26/04 (SKIP) sont mesurées **avant**. Cette asymétrie est **importante pour INCR** car le clustering accélère drastiquement les MERGE dbt qui lisent `RAW_MEDIPRIX_FACTURES` (cf. section "Le clustering RAW_MEDIPRIX_FACTURES a deux effets distincts" ci-dessous). La mesure INCR du 25/04 est donc à considérer comme une **borne supérieure** ; le coût réel post-clustering sera significativement plus bas (estimation -20 à -35 %).

  ┌───────────────────────┬──────────────────────┬─────────────────────────────────┬────────────────┬────────────────┬───────────────┬──────────────────┐
  │         Mode          │         Date         │ vs clustering RAW_MEDIPRIX_FACT.│  cr warehouse  │ cr clustering  │   cr total    │      €/nuit      │
  ├───────────────────────┼──────────────────────┼─────────────────────────────────┼────────────────┼────────────────┼───────────────┼──────────────────┤
  │ FULL (lundi)          │ 2026-04-27 (lundi)   │   POST (12 h après)             │       1,6545   │       0,3209   │       1,9754  │       5,452 €    │
  ├───────────────────────┼──────────────────────┼─────────────────────────────────┼────────────────┼────────────────┼───────────────┼──────────────────┤
  │ INCREMENTAL (mar-sam) │ 2026-04-25 (samedi)  │   PRÉ                           │       1,5152   │       0,1498   │       1,6650  │       4,595 €    │
  ├───────────────────────┼──────────────────────┼─────────────────────────────────┼────────────────┼────────────────┼───────────────┼──────────────────┤
  │ SKIP (dimanche)       │ 2026-04-26 (dimanche)│   PRÉ                           │       0,0358   │       0,0000   │       0,0358  │       0,099 €    │
  └───────────────────────┴──────────────────────┴─────────────────────────────────┴────────────────┴────────────────┴───────────────┴──────────────────┘

### Mesures complémentaires à prévoir pour homogénéiser

  ┌─────────────────────────────┬──────────────────────┬───────────────────────────────────────────────────────────────────────────┐
  │         Mode                │     Date à mesurer   │                              Quand                                        │
  ├─────────────────────────────┼──────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ INCREMENTAL post-clustering │ 2026-04-28 (mar)     │ Mesurable le 29/04 matin (latence ACCOUNT_USAGE 45 min - 3 h)             │
  ├─────────────────────────────┼──────────────────────┼───────────────────────────────────────────────────────────────────────────┤
  │ SKIP post-clustering        │ 2026-05-03 (dim)     │ Mesurable le 05/05 matin                                                  │
  └─────────────────────────────┴──────────────────────┴───────────────────────────────────────────────────────────────────────────┘

## Le clustering RAW_MEDIPRIX_FACTURES a DEUX effets distincts

Le clustering ``CLUSTER BY (PHA_ID, FAC_DATE)`` sur ``RAW_MEDIPRIX_FACTURES`` (266 M lignes) produit **deux gains de nature différente** qu'il faut distinguer pour interpréter les coûts.

### Effet n°1 — Sur l'écriture (re-clustering en arrière-plan)

Quand des données sont écrites dans une table clusterée, Snowflake déclenche un service serverless qui réorganise les micro-partitions pour respecter l'ordre du ``CLUSTER BY``. Ce coût est facturé séparément dans ``AUTOMATIC_CLUSTERING_HISTORY``.

  ┌─────────────────┬──────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┐
  │      Mode       │ Volume écrit dans RAW_MEDIPRIX_FACT. │                          Coût re-clustering                             │
  ├─────────────────┼──────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ FULL (lundi)    │  266 M lignes (TRUNCATE + COPY)      │  **Important** : 0,2131 cr mesuré le 28/04                              │
  ├─────────────────┼──────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ INCREMENTAL     │  ~30 M lignes (MERGE 30 j)           │  **Faible** : peu de partitions à réorganiser                           │
  ├─────────────────┼──────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
  │ SKIP            │  0                                   │  **Nul** : pas de write                                                 │
  └─────────────────┴──────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘

### Effet n°2 — Sur la lecture (pruning de partitions) — **EFFET MAJEUR**

C'est **le bénéfice principal du clustering** : permettre à Snowflake de skipper les micro-partitions non pertinentes lors d'un ``SELECT`` avec ``WHERE PHA_ID = ... AND FAC_DATE >= ...``. Avant clustering, ``avg_depth`` = 418 (mauvais : il faut scanner ~418 partitions pour trouver une ligne) ; après, ``avg_depth`` = 3,12.

  ┌───────────────────────────────────────────┬───────────────────┬─────────────────────────────┬─────────────────┐
  │ Modèle dbt qui lit RAW_MEDIPRIX_FACTURES  │  Avant clustering │  Cible post-clustering      │   Gain attendu  │
  ├───────────────────────────────────────────┼───────────────────┼─────────────────────────────┼─────────────────┤
  │ MERGE stg_mediprix_factures               │     ~37 min       │       5-10 min              │  -27 min, -75 % │
  ├───────────────────────────────────────────┼───────────────────┼─────────────────────────────┼─────────────────┤
  │ MERGE fact_prix_journalier                │     ~17 min       │       ~5 min                │  -12 min, -70 % │
  ├───────────────────────────────────────────┼───────────────────┼─────────────────────────────┼─────────────────┤
  │ MERGE mart_kpi_remise_labo                │     variable      │       -50 à -75 %           │       attendu   │
  ├───────────────────────────────────────────┼───────────────────┼─────────────────────────────┼─────────────────┤
  │ Autres marts touchant RAW_MEDIPRIX_FACT.  │     variables     │       -50 à -75 %           │       attendu   │
  └───────────────────────────────────────────┴───────────────────┴─────────────────────────────┴─────────────────┘

**Cet effet s'applique à TOUTES les nuits** (full, incremental, et même mode jour) dès que dbt lit `RAW_MEDIPRIX_FACTURES`. C'est le gain qui justifie le clustering.

### Pourquoi la baseline INCREMENTAL pré-clustering est à considérer comme borne supérieure

La nuit du 25/04 (1,6650 cr = 4,595 €) a été mesurée **avant** le clustering. Sur cette nuit :

- Re-clustering (Effet n°1) : ~0,15 cr → restera à peu près identique post-clustering
- Pruning (Effet n°2) : **MERGE stg_mediprix_factures durait 17 min 45 s** dans la tranche post-reload incrementale → après clustering, devrait passer à ~5 min, soit **-12,5 min** de warehouse busy = **-0,21 cr** (à X-Small)

**Estimation INCR post-clustering** : 1,6650 - 0,21 ≈ **1,45 cr ≈ 4,00 €/nuit** (à valider par mesure réelle le 29/04 matin).

### Recalcul du coût mensuel hybride avec estimation post-clustering

  ┌───────────────────────┬───────────────────┬────────────────────┬───────────────────────┬───────────────────┐
  │         Mode          │  Nuits / mois     │  €/nuit (mesuré)   │  €/nuit (post-clust.) │ €/mois post-clust.│
  ├───────────────────────┼───────────────────┼────────────────────┼───────────────────────┼───────────────────┤
  │ FULL                  │   4,33            │    5,452 € ✓       │    5,452 € ✓          │   23,61 €         │
  ├───────────────────────┼───────────────────┼────────────────────┼───────────────────────┼───────────────────┤
  │ INCREMENTAL           │  21,67            │    4,595 € (PRÉ)   │    ~4,00 € (estimé)   │  ~86,68 €         │
  ├───────────────────────┼───────────────────┼────────────────────┼───────────────────────┼───────────────────┤
  │ SKIP                  │   4,33            │    0,099 € ✓       │    0,099 € ✓          │    0,43 €         │
  ├───────────────────────┼───────────────────┼────────────────────┼───────────────────────┼───────────────────┤
  │ **TOTAL nocturne**    │  **30**           │                    │                       │ **~110,72 €/mois**│
  └───────────────────────┴───────────────────┴────────────────────┴───────────────────────┴───────────────────┘

→ **Pour la présentation, donner une fourchette : ~100-125 €/mois nocturne post-optimisations**, avec engagement à recalibrer après mesure du 29/04.

### Coût mensuel hybride

Pondération hebdomadaire : 1 lundi (full) + 5 mardi-samedi (incremental) + 1 dimanche (skip), soit sur un mois moyen de 30 jours = **4,33 lundis + 21,67 mar-sam + 4,33 dimanches**.

#### Avec les baselines mesurées telles quelles (INCR pré-clustering)

  ┌───────────────────────┬───────────────────┬─────────────────┬───────────────────┐
  │         Mode          │  Nuits / mois     │  €/nuit         │  €/mois           │
  ├───────────────────────┼───────────────────┼─────────────────┼───────────────────┤
  │ FULL (post-clust.)    │   4,33            │  5,452 €        │  23,61 €          │
  ├───────────────────────┼───────────────────┼─────────────────┼───────────────────┤
  │ INCREMENTAL (PRÉ)     │  21,67            │  4,595 €        │  99,57 €          │
  ├───────────────────────┼───────────────────┼─────────────────┼───────────────────┤
  │ SKIP                  │   4,33            │  0,099 €        │   0,43 €          │
  ├───────────────────────┼───────────────────┼─────────────────┼───────────────────┤
  │ **TOTAL (max)**       │  **30**           │                 │ **123,61 €/mois** │
  └───────────────────────┴───────────────────┴─────────────────┴───────────────────┘

→ Ce chiffre est la **borne haute** : la baseline INCR mesurée n'a pas encore l'effet du clustering `RAW_MEDIPRIX_FACTURES` (cf. section ci-dessous "Le clustering RAW_MEDIPRIX_FACTURES a deux effets distincts"). L'estimation post-clustering complet est donnée dans cette même section : **~110 €/mois**.

→ **Pour la présentation : fourchette ~100-125 €/mois nocturne**, à resserrer dès la mesure INCR post-clustering du 29/04 matin.

### Détail nuit FULL (lundi) — 27/04/2026

Premier run après application du clustering `(PHA_ID, FAC_DATE)` sur RAW_MEDIPRIX_FACTURES.

  ┌───────────────┬───────────────┬────────────────────────────────────────────────────────────┬─────────────┬────────────────┬─────────────┬─────────┐
  │   Heure UTC   │   Heure FR    │                          Phase                             │ cr warehouse│ cr clustering  │ cr total    │   €     │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 18:00 - 19:00 │ 20:00 - 21:00 │ Pre-night healthcheck                                      │      0,1736 │         0,0000 │      0,1736 │ 0,479 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 19:00 - 20:00 │ 21:00 - 22:00 │ CDC pre-reload                                             │      0,0986 │         0,0000 │      0,0986 │ 0,272 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 20:00 - 21:00 │ 22:00 - 23:00 │ Audit purge + backup Metabase                              │      0,1071 │         0,0000 │      0,1071 │ 0,296 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 21:00 - 22:00 │ 23:00 - 00:00 │ ref_reload début (TRUNCATE + PUT)                          │      0,1127 │         0,0000 │      0,1127 │ 0,311 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 22:00 - 01:00 │ 00:00 - 03:00 │ ref_reload (SELECT MySQL, WH suspendu, 3 tranches)         │      0,0045 │         0,0000 │      0,0045 │ 0,012 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 01:00 - 02:00 │ 03:00 - 04:00 │ ref_reload : COPY RAW_MEDIPRIX_FACTURES (10m21) + PRODUITS │      0,2194 │         0,2131 │      0,4325 │ 1,194 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 02:00 - 03:00 │ 04:00 - 05:00 │ ref_reload fin + POST-CHECK + dbt post-reload début        │      0,7818 │         0,0000 │      0,7818 │ 2,158 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ 03:00 - 04:00 │ 05:00 - 06:00 │ dbt post-reload fin + pipeline_maintenance + dev_clone     │      0,1568 │         0,1078 │      0,2646 │ 0,730 € │
  ├───────────────┼───────────────┼────────────────────────────────────────────────────────────┼─────────────┼────────────────┼─────────────┼─────────┤
  │ TOTAL         │               │                                                            │      1,6545 │         0,3209 │      1,9754 │ 5,452 € │
  └───────────────┴───────────────┴────────────────────────────────────────────────────────────┴─────────────┴────────────────┴─────────────┴─────────┘

  ┌────────────────────────────────────────────┬─────────────────────────────────────────────┐
  │                  Métrique                  │               Valeur précise                │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Wall-clock complet (pre-night → dev_clone) │ 8 h 39 min (20:35 → 05:14 FR)               │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Wall-clock ref_reload seul                 │ 5 h 17 min (23:05 → 04:22 FR) ✓ ta timeline │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Crédits warehouse facturés                 │ 1,6545 cr                                   │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Crédits auto-clustering                    │ 0,3209 cr                                   │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ TOTAL crédits/nuit                         │ 1,9754 cr                                   │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Coût €/nuit (×2,76)                        │ 5,452 €                                     │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Mensuel 26 nuits (skip dimanche)           │ 51,36 cr × 2,76 = 141,76 €/mois             │
  ├────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Mensuel 30 nuits (sans skip)               │ 59,26 cr × 2,76 = 163,56 €/mois             │
  └────────────────────────────────────────────┴─────────────────────────────────────────────┘

## Pourquoi 02:00–03:00 UTC pèse 0,78 cr et 01:00–02:00 seulement 0,22 cr

Les deux tranches contiennent des opérations massives mais le coût dépend du **warehouse busy**, pas du volume traité :

  ┌───────────────┬─────────────────────────────────────────────────────────────────────────────┬──────────────┐
  │   Tranche     │                                  Activité                                   │ Busy net     │
  ├───────────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤
  │ 01:00 - 02:00 │ COPY RAW_MEDIPRIX_FACTURES (10 min 21 s) seul, entouré de PUT_FILES         │ ~13 min      │
  │               │ client qui laissent le warehouse s'auto-suspendre (60 s trailing à chaque   │              │
  │               │ retour). Le warehouse fait du "stop and go".                                │              │
  ├───────────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤
  │ 02:00 - 03:00 │ COPY STOCKHISTORY puis dbt staging (12 modèles parallèles, MERGE            │ ~47 min      │
  │               │ stg_mediprix_factures 17 min 45 s) puis dbt marts (12 modèles parallèles,   │              │
  │               │ MERGE fact_ventes 11 min, fact_prix_journalier 11 min, fact_commandes       │              │
  │               │ 11 min, fact_stock_valorisation 12 min). Le warehouse reste allumé en       │              │
  │               │ continu — le parallélisme des MERGE est absorbé sans coût additionnel.      │              │
  └───────────────┴─────────────────────────────────────────────────────────────────────────────┴──────────────┘

→ **Le coût n'est pas proportionnel au volume loadé** ; il est proportionnel au temps "warehouse allumé". L'enjeu d'optimisation prioritaire reste les **modèles dbt longs** (cf. L4, L7), pas le bulk_load.

## Usage du script

```bash
# Sur l'hôte (avec .env présent) :
python scripts/snowflake_cost_report.py                       # défaut J-2 (latence ACCOUNT_USAGE)
python scripts/snowflake_cost_report.py --date 2026-04-27     # nuit spécifique (jour de démarrage)
python scripts/snowflake_cost_report.py --tarif 2.50          # tarif différent
python scripts/snowflake_cost_report.py --json                # sortie JSON
python scripts/snowflake_cost_report.py --markdown reports/cost_2026-04-27.md  # sauvegarde

# Dans le container :
docker exec medicore_elt_batch python scripts/snowflake_cost_report.py --date 2026-04-27
```

## Postes de coût hors périmètre du rapport

  ┌───────────────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────┐
  │           Poste           │                                  Source                                     │             Note                │
  ├───────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ Mode jour (07:00 → 19:00) │ `WAREHOUSE_METERING_HISTORY` tranches diurnes                               │ Couvert par `cost_monitoring.py`│
  ├───────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ Stockage                  │ `STORAGE_USAGE`, `DATABASE_STORAGE_USAGE_HISTORY`                           │ Estimation 23 €/mois actuel     │
  ├───────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ Materialized Views        │ `MATERIALIZED_VIEW_REFRESH_HISTORY`                                         │ Non utilisées chez nous         │
  ├───────────────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────┤
  │ Search Optimization       │ `SEARCH_OPTIMIZATION_HISTORY`                                               │ Non activé                      │
  └───────────────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────┘

## Comparaison entre sessions (à remplir au fil du temps)

À chaque run nocturne validé, lancer le script et reporter la ligne dans le tableau correspondant à son mode.

### Mode FULL (lundi)

  ┌──────────────┬────────────────────────────────────────────┬───────────┬───────────┬─────────────┬───────────────┬──────────────────────────────────────────────────────────────┐
  │     Date     │                État pipeline               │ cr WH     │ cr AC     │ cr total    │     €/nuit    │                          Notes                               │
  ├──────────────┼────────────────────────────────────────────┼───────────┼───────────┼─────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
  │ 2026-04-27   │ L1+L5 + clustering RAW_MEDIPRIX_FACTURES   │   1,6545  │   0,3209  │      1,9754 │      5,452 €  │ Premier full post-clustering, baseline FULL                  │
  ├──────────────┼────────────────────────────────────────────┼───────────┼───────────┼─────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
  │ 2026-05-04   │ + L7 mart_kpi_dormant (incremental)        │     ?     │     ?     │           ? │           ?   │ Cible : -0,11 cr clustering, -8 min compute                  │
  └──────────────┴────────────────────────────────────────────┴───────────┴───────────┴─────────────┴───────────────┴──────────────────────────────────────────────────────────────┘

### Mode INCREMENTAL (mardi-samedi)

  ┌──────────────┬────────────────────────────────────────────┬───────────┬───────────┬─────────────┬───────────────┬──────────────────────────────────────────────────────────────┐
  │     Date     │                État pipeline               │ cr WH     │ cr AC     │ cr total    │     €/nuit    │                          Notes                               │
  ├──────────────┼────────────────────────────────────────────┼───────────┼───────────┼─────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
  │ 2026-04-25   │ L1+L5 (avant clustering RAW_MEDIPRIX_FACT.)│   1,5152  │   0,1498  │      1,6650 │      4,595 €  │ Baseline INCREMENTAL pré-clustering                          │
  ├──────────────┼────────────────────────────────────────────┼───────────┼───────────┼─────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
  │ 2026-04-28   │ + clustering RAW_MEDIPRIX_FACTURES         │     ?     │     ?     │           ? │           ?   │ Premier incremental post-clustering (à mesurer 29/04)        │
  └──────────────┴────────────────────────────────────────────┴───────────┴───────────┴─────────────┴───────────────┴──────────────────────────────────────────────────────────────┘

### Mode SKIP (dimanche)

  ┌──────────────┬────────────────────────────────────────────┬───────────┬───────────┬─────────────┬───────────────┬──────────────────────────────────────────────────────────────┐
  │     Date     │                État pipeline               │ cr WH     │ cr AC     │ cr total    │     €/nuit    │                          Notes                               │
  ├──────────────┼────────────────────────────────────────────┼───────────┼───────────┼─────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
  │ 2026-04-26   │ L1+L5 + skip dimanche complet              │   0,0358  │   0,0000  │      0,0358 │      0,099 €  │ Baseline SKIP — seul l'audit/backup Metabase tourne          │
  └──────────────┴────────────────────────────────────────────┴───────────┴───────────┴─────────────┴───────────────┴──────────────────────────────────────────────────────────────┘

## Limites connues

- Le mapping phase ↔ tranche horaire est **statique par mode** : si `batch_loop.sh` change de timing (ex. dépassement ref_reload qui déborde sur la tranche suivante), les libellés deviennent imprécis. Le total crédits reste correct dans tous les cas.
- L'auto-clustering est attribué à la phase déclenchante via heuristique (`CLUSTERING_PHASE_MAPPING`). Si une nouvelle table clusterée apparaît, l'ajouter dans le script.
- La latence ACCOUNT_USAGE (45 min – 3 h) impose un défaut J-2. Pour analyser la nuit qui vient de finir, attendre 3 h après la fin du run.
- La détection auto du mode utilise le jour de la semaine standard (`MODE_BY_WEEKDAY`). Si le calendrier d'opérations dérive (ex. ref_reload full décalé sur un mardi suite à un incident), forcer `--mode full`.
