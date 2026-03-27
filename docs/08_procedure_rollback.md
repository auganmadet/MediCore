# Procédure de rollback — MediCore PROD

## Table des matières

1. [Quand utiliser cette procédure](#quand-utiliser-cette-procédure)
2. [Détecter le problème](#1-détecter-le-problème)
3. [Évaluer l'impact](#2-évaluer-limpact)
4. [Restaurer via Snowflake Time Travel](#3-restaurer-via-snowflake-time-travel)
   - [Restaurer un modèle MARTS](#3a-restaurer-un-modèle-marts-cas-le-plus-fréquent)
   - [Restaurer un modèle STAGING](#3b-restaurer-un-modèle-staging)
   - [Restaurer une table RAW](#3c-restaurer-une-table-raw-après-bulk_load-corrompu)
   - [Restaurer plusieurs modèles](#3d-restaurer-plusieurs-modèles-à-la-fois)
5. [Alternative : re-run du modèle corrigé](#4-alternative--re-run-du-modèle-corrigé)
6. [Investiguer la cause](#5-investiguer-la-cause)
   - [Historique des runs dbt](#5a-consulter-lhistorique-des-runs-dbt)
   - [Query_history Snowflake](#5b-consulter-le-query_history-snowflake)
   - [Fichiers dbt](#5c-consulter-les-fichiers-dbt)
   - [Commit fautif](#5d-identifier-le-commit-fautif)
7. [Prévenir la récurrence](#6-prévenir-la-récurrence)
8. [Checklist rapide](#7-checklist-rapide)
9. [Limitations](#8-limitations)

---

## Quand utiliser cette procédure

Un modèle dbt bugué a été déployé en production (`dbt run --target prod`) et
les dashboards Metabase affichent des données incorrectes (KPIs à 0, doublons,
valeurs aberrantes, données manquantes).

**Objectif** : restaurer les données correctes en moins de 15 minutes.

[↑ Retour au sommaire](#table-des-matières)

---

## 1. Détecter le problème

  ┌──────────────────────────────────┬────────────────────────────────────────┐
  │ Signal                           │ Source                                 │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ Alerte Teams "dbt test failed"   │ batch_loop.sh (automatique)            │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ Utilisateur signale des données  │ Pharmacien, GIE, équipe IT             │
  │ incorrectes sur Metabase         │                                        │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ KPIs à 0 ou valeurs aberrantes   │ Vérification manuelle dashboard        │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ Erreurs dans les logs conteneur  │ docker logs medicore_elt_batch         │
  └──────────────────────────────────┴────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 2. Évaluer l'impact

Identifier les modèles affectés et la couche concernée :

```sql
-- Quels modèles ont été exécutés récemment ?
SELECT *
FROM MEDICORE_PROD.AUDIT.PIPELINE_STEP_RUNS
WHERE STEP_START > DATEADD('hour', -6, CURRENT_TIMESTAMP())
ORDER BY STEP_START DESC;
```

  ┌────────────────────┬─────────────────────────────────────────────────────┐
  │ Couche affectée    │ Impact                                              │
  ├────────────────────┼─────────────────────────────────────────────────────┤
  │ STAGING seulement  │ Modéré — les MARTS ne sont pas encore recalculés    │
  │                    │ si le cycle dbt n'a pas encore atteint les marts    │
  ├────────────────────┼─────────────────────────────────────────────────────┤
  │ MARTS (faits/dims) │ Élevé — les dashboards Metabase lisent MARTS        │
  │                    │ directement, les utilisateurs voient les erreurs    │
  ├────────────────────┼─────────────────────────────────────────────────────┤
  │ RAW                │ Critique — si le bulk_load a corrompu RAW,          │
  │                    │ toute la chaîne en aval est affectée                │
  └────────────────────┴─────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 3. Restaurer via Snowflake Time Travel

**Fenêtre disponible : 1 jour** (DATA_RETENTION_TIME_IN_DAYS = 1, Standard Edition).

Au-delà de 24h, la restauration Time Travel n'est plus possible.

### 3a. Restaurer un modèle MARTS (cas le plus fréquent)

```sql
-- Identifier le timestamp avant le dbt run fautif
-- (consulter AUDIT.PIPELINE_STEP_RUNS ou git log pour l'heure du déploiement)

-- Restaurer fact_ventes à son état d'avant le run
CREATE OR REPLACE TABLE MEDICORE_PROD.MARTS.FACT_VENTES
  CLONE MEDICORE_PROD.MARTS.FACT_VENTES
  AT (TIMESTAMP => '2026-03-25 10:00:00'::TIMESTAMP_LTZ);

-- Vérification rapide
SELECT COUNT(*) FROM MEDICORE_PROD.MARTS.FACT_VENTES;
```

### 3b. Restaurer un modèle STAGING

```sql
CREATE OR REPLACE TABLE MEDICORE_PROD.STAGING.STG_MEDIPRIX_FACTURES
  CLONE MEDICORE_PROD.STAGING.STG_MEDIPRIX_FACTURES
  AT (TIMESTAMP => '2026-03-25 10:00:00'::TIMESTAMP_LTZ);
```

### 3c. Restaurer une table RAW (après bulk_load corrompu)

```sql
CREATE OR REPLACE TABLE MEDICORE_PROD.RAW.RAW_ORDERS
  CLONE MEDICORE_PROD.RAW.RAW_ORDERS
  AT (TIMESTAMP => '2026-03-25 10:00:00'::TIMESTAMP_LTZ);
```

**Après restauration RAW** : relancer la chaîne dbt pour propager les données
corrigées vers STAGING et MARTS :

```bash
docker exec medicore_elt_batch bash -c "cd /app/dbt && \
  dbt run --select tag:staging --target prod && \
  dbt run --select tag:marts --target prod"
```

### 3d. Restaurer plusieurs modèles à la fois

```sql
-- Script de restauration groupée (adapter le timestamp)
SET TS = '2026-03-25 10:00:00'::TIMESTAMP_LTZ;

CREATE OR REPLACE TABLE MEDICORE_PROD.MARTS.FACT_VENTES
  CLONE MEDICORE_PROD.MARTS.FACT_VENTES AT (TIMESTAMP => $TS);
CREATE OR REPLACE TABLE MEDICORE_PROD.MARTS.FACT_COMMANDES
  CLONE MEDICORE_PROD.MARTS.FACT_COMMANDES AT (TIMESTAMP => $TS);
CREATE OR REPLACE TABLE MEDICORE_PROD.MARTS.MART_KPI_OPERATEUR
  CLONE MEDICORE_PROD.MARTS.MART_KPI_OPERATEUR AT (TIMESTAMP => $TS);

-- Vérification
SELECT 'FACT_VENTES' as t, COUNT(*) as rows FROM MEDICORE_PROD.MARTS.FACT_VENTES
UNION ALL
SELECT 'FACT_COMMANDES', COUNT(*) FROM MEDICORE_PROD.MARTS.FACT_COMMANDES
UNION ALL
SELECT 'MART_KPI_OPERATEUR', COUNT(*) FROM MEDICORE_PROD.MARTS.MART_KPI_OPERATEUR;
```

[↑ Retour au sommaire](#table-des-matières)

---

## 4. Alternative : re-run du modèle corrigé

Si le code dbt a été corrigé (fix commité et poussé), la restauration n'est
pas nécessaire — il suffit de relancer le modèle corrigé :

```bash
# Corriger le code, commiter, puis :
docker exec medicore_elt_batch bash -c "cd /app/dbt && \
  dbt run --select <modele_corrige>+ --target prod"
```

Le `+` après le modèle relance aussi tous les modèles en aval (propagation).

[↑ Retour au sommaire](#table-des-matières)

---

## 5. Investiguer la cause

### 5a. Consulter l'historique des runs dbt

```sql
-- Derniers runs avec erreurs
SELECT RUN_ID, STATUS, RUN_START, RUN_END
FROM MEDICORE_PROD.AUDIT.PIPELINE_RUNS
WHERE STATUS != 'SUCCESS'
ORDER BY RUN_START DESC
LIMIT 10;
```

### 5b. Consulter le query_history Snowflake

```sql
-- Requêtes dbt récentes qui ont échoué
SELECT QUERY_TEXT, ERROR_MESSAGE, START_TIME, END_TIME
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
  RESULT_LIMIT => 50,
  END_TIME_RANGE_START => DATEADD('hour', -6, CURRENT_TIMESTAMP())
))
WHERE ERROR_MESSAGE IS NOT NULL
ORDER BY START_TIME DESC;
```

### 5c. Consulter les fichiers dbt

```bash
# Résultats du dernier run
cat /app/dbt/target/run_results.json | python3 -m json.tool | head -50

# Logs dbt
tail -100 /app/dbt/logs/dbt.log
```

### 5d. Identifier le commit fautif

```bash
# Quel commit a modifié le modèle ?
git log --oneline --follow dbt/models/marts/<modele>.sql

# Différence avec la version précédente
git diff HEAD~1 dbt/models/marts/<modele>.sql
```

[↑ Retour au sommaire](#table-des-matières)

---

## 6. Prévenir la récurrence

  ┌────────────────────────────────────┬─────────────────────────────────────────┐
  │ Mesure                             │ Détail                                  │
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Tests dbt avant déploiement        │ CI exécute `dbt test` sur MEDICORE_TEST │
  │                                    │ avant merge sur main                    │
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Singular tests sur les KPIs        │ 16 tests vérifient les calculs métier   │
  │                                    │ (marge, stock, ABC, etc.)               │
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Branch protection sur main         │ PR + CI verte obligatoire               │
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Guard full_refresh                 │ Macro guard_full_refresh empêche les    │
  │                                    │ full-refresh accidentels sur high_volume│
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Guard seed prod                    │ Macro guard_seed_prod empêche dbt seed  │
  │                                    │ sur l'environnement prod                │
  ├────────────────────────────────────┼─────────────────────────────────────────┤
  │ Review du code dbt                 │ Vérifier les jointures, les filtres,    │
  │                                    │ les agrégations avant merge             │
  └────────────────────────────────────┴─────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 7. Checklist rapide

En cas d'incident, suivre dans l'ordre :

```
[ ] 1. Identifier le(s) modèle(s) affecté(s)
[ ] 2. Identifier le timestamp du dernier état correct
[ ] 3. Restaurer via Time Travel (CLONE ... AT TIMESTAMP)
[ ] 4. Vérifier les row counts post-restauration
[ ] 5. Rafraîchir un dashboard Metabase pour confirmer
[ ] 6. Investiguer la cause (query_history, git log)
[ ] 7. Corriger le code, commiter, pousser
[ ] 8. Relancer dbt run sur le modèle corrigé
[ ] 9. Documenter l'incident (CHANGELOG.md)
```

[↑ Retour au sommaire](#table-des-matières)

---

## 8. Limitations

- **Time Travel : 1 jour max** (Standard Edition, DATA_RETENTION = 1).
  Au-delà, la restauration nécessite un re-run complet depuis RAW.
- **Les vues STAGING** ne supportent pas Time Travel (pas de données
  stockées). Restaurer la table RAW source puis relancer dbt staging.
- **Les snapshots SCD2** ne sont pas restaurables via Time Travel sans
  perdre l'historique accumulé. Privilégier un re-run depuis staging.

[↑ Retour au sommaire](#table-des-matières)

---

## Voir aussi

- [Opérations](03_operations.md) — exploitation normale et monitoring
