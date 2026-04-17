# Maintenance automatique du pipeline MediCore

## Table des matières

1. [En temps normal : un seul script](#en-temps-normal--un-seul-script)
2. [Architecture de l'orchestrateur](#architecture-de-lorchestateur)
3. [Les 5 phases](#les-5-phases)
4. [Modes d'exécution --fix-safe vs --fix](#modes-dexécution---fix-safe-vs---fix)
5. [Intégration batch_loop.sh](#intégration-batch_loopsh)
6. [Checklist par symptôme](#checklist-par-symptôme)
7. [Annexe A — Dictionnaire des scripts](#annexe-a--dictionnaire-des-scripts)
8. [Annexe B — Référence des problèmes par phase](#annexe-b--référence-des-problèmes-par-phase)

---

## En temps normal : un seul script

```bash
python scripts/pipeline_maintenance.py --fix-safe
```

Ce script orchestre les 5 phases de maintenance du pipeline MediCore. Il s'auto-authentifie via `.env`, détecte et corrige les problèmes automatiquement. Il tourne chaque nuit à 05h00 dans `batch_loop.sh`.

Autres modes d'exécution :

```bash
# Simulation : détecte sans corriger
python scripts/pipeline_maintenance.py --dry-run

# Tous les fix (y compris reloads lourds) — mode manuel
python scripts/pipeline_maintenance.py --fix

# Une seule phase
python scripts/pipeline_maintenance.py --phase healthcheck
python scripts/pipeline_maintenance.py --phase cdc
python scripts/pipeline_maintenance.py --phase bulk
python scripts/pipeline_maintenance.py --phase dbt
python scripts/pipeline_maintenance.py --phase metabase
```

[↑ Retour au sommaire](#table-des-matières)

---

## Architecture de l'orchestrateur

```
scripts/pipeline_maintenance.py (orchestrateur global)
  │
  ├── S'auto-authentifie (Snowflake + Metabase + Kafka via .env)
  │
  ├── Phase 1 : healthcheck_maintenance.py (H1-H7)
  │   └── Si H1/H2/H3 échouent → les phases suivantes continuent
  │
  ├── Phase 2 : cdc_maintenance.py (C1-C6)
  │
  ├── Phase 3 : bulk_maintenance.py (B1-B6)
  │
  ├── Phase 4 : dbt_maintenance.py (D1-D6)
  │
  ├── Phase 5 : metabase_maintenance.py (P1-P10)
  │
  └── Rapport global (OK / FAIL / WARN / SKIP par phase)
```

Chaque script reste utilisable individuellement pour le dépannage ponctuel. L'orchestrateur les appelle en séquence et gère les timeouts par phase.

[↑ Retour au sommaire](#table-des-matières)

---

## Les 5 phases

### Phase 1 — Healthcheck (connectivité)

Vérifie la connectivité de tous les services du pipeline.

  ┌─────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction --fix-safe                             │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H1  │ MySQL RDS inaccessible           │ Alerte (infrastructure AWS)                       │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H2  │ Kafka broker down                │ Restart Kafka + Zookeeper (sauf si logs "corrupt") │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H3  │ Snowflake inaccessible           │ Resume warehouse + vérification credits            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H4  │ Warehouse suspendu               │ Resume automatique                                │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H5  │ Metabase API inaccessible        │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H6  │ Debezium connector FAILED        │ Restart automatique                               │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ H7  │ Permissions Snowflake insuffisantes │ Alerte                                         │
  └─────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

**Script** : `scripts/healthcheck_maintenance.py`

### Phase 2 — CDC (Kafka / Debezium)

Vérifie l'état du pipeline CDC (Change Data Capture).

  ┌─────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction --fix-safe                             │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C1  │ Kafka lag excessif par topic     │ Alerte si > seuil                                 │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C2  │ DLQ en croissance                │ Purge automatique > 90 jours                      │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C3  │ Doublons dans RAW CDC            │ Alerte (dédup gérée par dbt staging)              │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C4  │ Debezium connector en erreur     │ Restart automatique                               │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C5  │ Topics Kafka vides               │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ C6  │ Offsets Kafka non commités       │ Alerte                                            │
  └─────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

**Script** : `scripts/cdc_maintenance.py`

### Phase 3 — Bulk Load (RAW)

Vérifie l'état des tables RAW après bulk load.

  ┌─────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction                                        │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B1  │ Lock file périmé                 │ --fix-safe : suppression automatique               │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B2  │ Tables RAW vides                 │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B3  │ Doublons tables référence        │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B4  │ Réconciliation MySQL/Snowflake   │ --fix uniquement : CLONE+SWAP par table            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B5  │ Données périmées (> 48h)         │ --fix uniquement : CLONE+SWAP 14 tables            │
  │     │                                  │ --fix-safe : alerte (rechargement par batch_loop)  │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B6  │ Schema drift MySQL/Snowflake     │ --fix-safe : ALTER TABLE avec type détecté MySQL   │
  └─────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

**Script** : `scripts/bulk_maintenance.py`
**Pattern CLONE+SWAP** : backup zero-copy avant TRUNCATE, rollback instantané si échec.

### Phase 4 — dbt (Staging / MARTS)

Vérifie l'état des modèles et tests dbt.

  ┌─────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction                                        │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D1  │ Modèles dbt en erreur            │ --fix uniquement : relance dbt run+test            │
  │     │                                  │ --fix-safe : alerte                                │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D2  │ Tests dbt échoués                │ --fix uniquement : relance dbt run+test            │
  │     │                                  │ (1 seul retry/jour, flag anti-boucle)             │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D3  │ Source freshness dépassée        │ --fix-safe : relance dbt source freshness          │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D4  │ Modèles skipped                  │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D5  │ Tables MARTS vides               │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D6  │ Row Access Policies              │ Informatif (dormantes, Alternative A)             │
  └─────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

**Script** : `scripts/dbt_maintenance.py`

### Phase 5 — Metabase (BI)

Détecte et corrige 10 problèmes Metabase. Voir `docs/15_metabase_checklist_depannage.md` pour le détail P1-P10.

**Script** : `scripts/metabase_maintenance.py`

[↑ Retour au sommaire](#table-des-matières)

---

## Modes d'exécution --fix-safe vs --fix

  ┌─────────────────────────────────────┬─────────────────────┬─────────────────────┐
  │ Fix                                 │ --fix-safe (05h00)  │ --fix (manuel)      │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ H2 Restart Kafka                    │ Oui (sauf corrupt)  │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ H3 Reconnexion Snowflake            │ Oui (sauf credits)  │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ H4 Resume warehouse                 │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ H6 Restart Debezium                 │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ C2 Purge DLQ > 90j                  │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ C4 Restart Debezium                 │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ B1 Supprime lock périmé             │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ B4 Reconciliation (CLONE+SWAP)      │ Alerte seulement    │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ B5 Ref reload (CLONE+SWAP)          │ Alerte seulement    │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ B6 Schema drift (ALTER TABLE)       │ Oui (type détecté)  │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ D1/D2 Relance dbt run+test          │ Alerte seulement    │ Oui (1 retry/jour)  │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ D3 Relance freshness                │ Oui                 │ Oui                 │
  ├─────────────────────────────────────┼─────────────────────┼─────────────────────┤
  │ P1-P10 Metabase                     │ Oui                 │ Oui                 │
  └─────────────────────────────────────┴─────────────────────┴─────────────────────┘

**--fix-safe** : corrections sures uniquement, pas de reload lourd (B4/B5/D1-D2 = alerte). C'est le mode utilisé par `batch_loop.sh` à 05h00.

**--fix** : tous les fix y compris les reloads lourds avec garde-fous CLONE+SWAP. Mode manuel uniquement.

[↑ Retour au sommaire](#table-des-matières)

---

## Intégration batch_loop.sh

```
NUIT (21h → 07h)
━━━━━━━━━━━━━━━━
00h00  Reset flags quotidiens
00h30  CDC pré-reload (vider backlog Kafka)
01h00  ref_reload 14 tables référence (~3h, TRUNCATE + bulk_load)
04h30  CDC + dbt post-reload (staging + snapshots + marts + tests + freshness)
05h00  ★ pipeline_maintenance.py --fix-safe ★
         → Phase 1 : healthcheck (H1-H7)
         → Phase 2 : CDC (C1-C6)
         → Phase 3 : bulk (B1-B6, alerte seulement pour B4/B5)
         → Phase 4 : dbt (D1-D6, alerte seulement pour D1/D2)
         → Phase 5 : Metabase (P1-P10 + provisionnement pharmacies)
         → Rapport global
```

Le ref_reload (01h00) utilise `HOUR >= REF_RELOAD_HOUR` pour ne pas manquer la fenêtre avec le sleep 10 min en mode nuit.

[↑ Retour au sommaire](#table-des-matières)

---

## Checklist par symptôme

### Le pipeline ne charge plus de données depuis plusieurs jours

```
Cause probable : B5 (données périmées) + ref_reload qui ne tourne pas

1. Vérifier les logs : docker logs --since 12h medicore_elt_batch | grep ref_reload
2. Si ref_reload n'a pas tourné : vérifier HOUR et REF_RELOAD_HOUR
3. Lancer manuellement :
   docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --fix
   → B5 relance le ref_reload avec CLONE+SWAP (14 tables, ~3h)
```

### Debezium est en FAILED

```
Cause probable : H6 / C4

1. Lancer : docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --fix-safe
   → H6 restart automatique

2. Si persiste : vérifier les logs Kafka Connect
   curl -s http://localhost:8083/connectors/winstat-mysql-connector/status
```

### Un service Docker ne démarre pas

```
1. docker compose ps → identifier le service en erreur
2. docker logs <service> → lire l'erreur
3. Lancer le healthcheck :
   docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --phase healthcheck --fix-safe
```

### Les dashboards Metabase affichent des erreurs

```
Voir docs/15_metabase_checklist_depannage.md
Lancer : docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --phase metabase
```

### Les tests dbt échouent

```
1. Lancer la phase dbt :
   docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --phase dbt --fix-safe
   → D3 freshness recalculée

2. Si les tests échouent toujours (problème non transitoire) :
   docker exec -it medicore_elt_batch python //app/scripts/pipeline_maintenance.py --phase dbt --fix
   → D1/D2 relance dbt run+test (1 retry avec flag anti-boucle)
```

### Compte Snowflake verrouillé

```
Cause : trop de tentatives de connexion échouées (scripts en boucle de retry)

1. Attendre 15-30 min (déverrouillage automatique)
2. Ou via la console Snowflake web :
   ALTER USER AUGUSTIN SET MINS_TO_UNLOCK = 0;
3. Relancer le conteneur :
   docker compose restart medicore-elt-batch
```

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe A — Dictionnaire des scripts

### Scripts de maintenance (appelés par pipeline_maintenance.py)

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Script                              │ Rôle                                             │ Usage                                            │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ healthcheck_maintenance.py          │ Connectivité MySQL, Kafka, Snowflake, Metabase,  │ python scripts/healthcheck_maintenance.py         │
  │                                     │ Debezium, permissions                            │ [--fix-safe] [--fix]                             │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ cdc_maintenance.py                  │ Lag Kafka, DLQ, doublons CDC, Debezium, offsets  │ python scripts/cdc_maintenance.py                 │
  │                                     │                                                  │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ bulk_maintenance.py                 │ Lock, tables vides, doublons, réconciliation,    │ python scripts/bulk_maintenance.py                │
  │                                     │ timestamps, schema drift                         │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ dbt_maintenance.py                  │ Modèles en erreur, tests échoués, freshness,     │ python scripts/dbt_maintenance.py                 │
  │                                     │ tables MARTS vides                               │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ metabase_maintenance.py             │ P1-P10 (cartes, filtres, embedding,              │ python scripts/metabase_maintenance.py            │
  │                                     │ provisionnement pharmacies)                      │ [--dry-run] [--diagnose --card/--dashboard]       │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┴──────────────────────────────────────────────────┘

### Scripts Metabase individuels

Voir `docs/15_metabase_checklist_depannage.md` pour la liste complète (20+ scripts de diagnostic et correction).

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe B — Référence des problèmes par phase

### Phase 1 — Healthcheck (H1-H7)

  ┌─────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
  │  #  │ Problème                    │ Détail                                                              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H1  │ MySQL RDS inaccessible      │ Infrastructure AWS. Vérifier instance RDS, credentials, VPC.        │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H2  │ Kafka broker down           │ Restart automatique. Garde-fou : vérifie logs pour "corrupt"        │
  │     │                             │ avant restart. Si corrompu → intervention manuelle.                  │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H3  │ Snowflake inaccessible      │ Resume warehouse + vérification credits. Si credits épuisés →       │
  │     │                             │ alerte sans fix.                                                     │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H4  │ Warehouse suspendu          │ Resume automatique (auto-suspend normal, pas une erreur).            │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H5  │ Metabase API inaccessible   │ Vérifier que le conteneur Metabase tourne : docker compose ps       │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H6  │ Debezium connector FAILED   │ Restart automatique. Cause fréquente : KafkaSchemaHistory           │
  │     │                             │ ThreadPoolExecutor terminé (problème connu Debezium).                │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H7  │ Permissions insuffisantes   │ SELECT test sur RAW/STAGING/MARTS. Si échec → vérifier les          │
  │     │                             │ GRANTS dans DDL_WH.sql.                                             │
  └─────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

### Phase 2 — CDC (C1-C6)

  ┌─────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
  │  #  │ Problème                    │ Détail                                                              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C1  │ Kafka lag excessif          │ Lag par topic > KAFKA_LAG_THRESHOLD (défaut 10000). Les CDC         │
  │     │                             │ tables ne sont pas à jour.                                          │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C2  │ DLQ en croissance           │ Events CDC malformés accumulés. Purge auto > 90 jours.              │
  │     │                             │ Seuil : DLQ_THRESHOLD (défaut 100).                                 │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C3  │ Doublons dans RAW CDC       │ Informatif. La dédup est gérée par dbt staging (ROW_NUMBER).        │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C4  │ Debezium en erreur          │ Restart automatique (identique à H6).                               │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C5  │ Topics Kafka vides          │ Aucun message dans les topics CDC → vérifier Debezium.              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ C6  │ Offsets non commités        │ Le consumer n'a jamais commité sur certaines partitions.            │
  └─────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

### Phase 3 — Bulk Load (B1-B6)

  ┌─────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
  │  #  │ Problème                    │ Détail                                                              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B1  │ Lock file périmé            │ /tmp/bulk_load.lock existe mais le PID est mort. Supprimé auto.     │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B2  │ Tables RAW vides            │ Alerte — une table RAW a 0 lignes après un reload.                  │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B3  │ Doublons tables référence   │ Détecte via GROUP BY ... HAVING COUNT > 1 sur les 14 tables ref.   │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B4  │ Réconciliation MySQL/SF     │ Compare COUNT MySQL vs Snowflake sur 5 tables principales.          │
  │     │                             │ --fix : CLONE+SWAP par table (backup zero-copy, rollback si échec). │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B5  │ Données périmées            │ CDC_TIMESTAMP > 48h sur les tables RAW.                             │
  │     │                             │ --fix : CLONE+SWAP 14 tables ref (table par table, rollback auto).  │
  │     │                             │ --fix-safe : alerte (rechargement par batch_loop.sh 01h00).          │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B6  │ Schema drift MySQL/SF       │ Colonnes ajoutées/supprimées dans MySQL pas reflétées dans          │
  │     │                             │ Snowflake. Fix : ALTER TABLE ADD COLUMN avec type détecté MySQL.    │
  └─────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

### Phase 4 — dbt (D1-D6)

  ┌─────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
  │  #  │ Problème                    │ Détail                                                              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D1  │ Modèles dbt en erreur       │ Parse run_results.json. Affiche le modèle + message d'erreur.      │
  │     │                             │ --fix : relance dbt run+test (1 retry/jour, flag anti-boucle).      │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D2  │ Tests dbt échoués           │ Idem D1. Compare avant/après : si même nb erreurs → non transitoire │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D3  │ Source freshness dépassée   │ dbt source freshness recalculée automatiquement (--fix-safe).       │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D4  │ Modèles skipped             │ Informatif — modèles non exécutés lors du dernier run.              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D5  │ Tables MARTS vides          │ Alerte si une des 32 tables MARTS a 0 lignes.                       │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D6  │ Row Access Policies         │ Informatif. Policies dormantes (Alternative A Metabase).            │
  └─────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

### Phase 5 — Metabase (P1-P10)

Voir `docs/15_metabase_checklist_depannage.md` pour le détail complet.

[↑ Retour au sommaire](#table-des-matières)
