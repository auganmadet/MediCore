# Maintenance automatique du pipeline MediCore

## Table des matières

1. [Architecture de surveillance en 4 niveaux](#architecture-de-surveillance-en-4-niveaux)
2. [Niveau 1 — Pre-night healthcheck](#niveau-1--pre-night-healthcheck)
3. [Niveaux 2a et 2b — Post-checks inline](#niveaux-2a-et-2b--post-checks-inline)
4. [Niveau 3 — Pipeline maintenance post-exécution](#niveau-3--pipeline-maintenance-post-exécution)
5. [Modes d'exécution --fix-safe vs --fix](#modes-dexécution---fix-safe-vs---fix)
6. [Intégration batch_loop.sh](#intégration-batch_loopsh)
7. [Checklist par symptôme](#checklist-par-symptôme)
8. [Annexe A — Dictionnaire des scripts](#annexe-a--dictionnaire-des-scripts)
9. [Annexe B — Référence des problèmes par phase](#annexe-b--référence-des-problèmes-par-phase)

---

## Architecture de surveillance en 4 niveaux

La maintenance automatique MediCore s'articule en 4 niveaux complémentaires, chacun avec un rôle précis dans le cycle nocturne :

  ┌──────────┬─────────────┬──────────────────────┬──────────────────────────────────┐
  │ Niveau   │ Heure FR    │ Script               │ Rôle                             │
  ├──────────┼─────────────┼──────────────────────┼──────────────────────────────────┤
  │    1     │ 20h30       │ pre_night_healthcheck│ Infra + config + auto-fix        │
  │          │             │ .py --fix            │ Go/no-go pour la nuit            │
  ├──────────┼─────────────┼──────────────────────┼──────────────────────────────────┤
  │   2a     │ 21h35       │ inline batch_loop    │ Post-check CDC pré-reload        │
  │          │             │ (post_check_cdc_     │ Warning non bloquant             │
  │          │             │ prereload)           │                                  │
  ├──────────┼─────────────┼──────────────────────┼──────────────────────────────────┤
  │   2b     │ ~23h16      │ inline batch_loop    │ Post-check ref_reload            │
  │          │             │ (post_check_ref_     │ BLOQUANT : skip dbt si KO        │
  │          │             │ reload)              │                                  │
  ├──────────┼─────────────┼──────────────────────┼──────────────────────────────────┤
  │    3     │ ~23h47      │ pipeline_maintenance │ Audit post-exécution             │
  │          │             │ .py --fix-safe       │ 4 phases : CDC, Bulk, dbt, MB    │
  └──────────┴─────────────┴──────────────────────┴──────────────────────────────────┘

Les horaires 2b et 3 sont calculés en mode incremental (L1+L5, depuis 2026-04-23). En mode full (lundi ou avant optimisation), le ref_reload prend ~4h48 → 2b vers 03h48 FR et 3 vers 04h18 FR.

### Pourquoi 4 niveaux et pas un seul ?

  ┌──────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Niveau                   │ Apport unique                                                                                                       │
  ├──────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ **1** (pre-night)        │ Empêche de démarrer la nuit si l'infra est KO. Corrige les dérives (`.env`, schéma CDC, `_BACKUP` résiduels).       │
  ├──────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ **2a** (post-CDC         │ Détecte un consumer bloqué AVANT le ref_reload. Alerte Teams dès 21h40 FR au lieu du lendemain matin.               │
  │       pré-reload)        │                                                                                                                     │
  ├──────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ **2b** (post-ref_reload) │ **Fail-fast** : si ref_reload a silencieusement échoué (table vide), skip dbt post-reload → évite MARTS corrompus.  │
  ├──────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ **3** (audit final)      │ Rapport consolidé post-nuit (tests dbt, freshness, doublons, MARTS vides). Enchaîné après dbt post-reload.          │
  └──────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Chaque niveau attrape des défaillances que les autres ne peuvent pas voir. Ils sont complémentaires, pas redondants.

[↑ Retour au sommaire](#table-des-matières)

---

## Niveau 1 — Pre-night healthcheck

Exécuté à **20h30 FR (18h30 UTC)** par `batch_loop.sh`, **30 min avant le passage en mode nuit**. Valide que l'infrastructure et la configuration sont prêtes pour la séquence nocturne critique, et corrige automatiquement ce qui peut l'être.

```bash
# Usage manuel
python scripts/pre_night_healthcheck.py              # check uniquement
python scripts/pre_night_healthcheck.py --fix        # check + auto-fix
```

### 14 checks (N1 à N8)

  ┌──────┬──────────────────────────┬───────────────────────────────────────────────┐
  │  #   │ Check                    │ Auto-fix                                      │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │ H1-7 │ Infrastructure           │ H2 restart Kafka, H3 reconnexion Snowflake,   │
  │      │ (MySQL, Kafka, Snowflake,│ H4 resume warehouse, H6 restart Debezium      │
  │      │ Metabase, Debezium,      │ (H1/H5/H7 alerte humaine si fail)             │
  │      │ permissions)             │                                               │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N2  │ Config Debezium          │ PUT config correcte (topic.prefix,            │
  │      │                          │ table.include.list, snapshot.mode)            │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N3  │ Env vars critiques `.env`│ Path.write_text() + flag restart_required     │
  │      │ (REF_RELOAD_HOUR,        │ (docker-compose ne relit .env sans restart)   │
  │      │ CDC_KAFKA_TOPIC_PREFIX…) │                                               │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N4  │ Code fixes présents dans │ Alerte humaine (rebuild si volume absent).    │
  │      │ le conteneur             │ `./scripts` volume-mounted → détection live   │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N5  │ Lock file non périmé     │ `os.remove()` si PID mort                     │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N6  │ Pas de `_BACKUP`         │ `DROP TABLE _BACKUP` (reliquat CLONE+SWAP     │
  │      │ résiduel en Snowflake    │ avorté)                                       │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N7  │ Schéma CDC uniforme      │ `ALTER TABLE DROP COLUMN` pour colonnes en    │
  │      │ (3 cols sur 4 tables RAW)│ trop (colonnes manquantes → alerte humaine)   │
  ├──────┼──────────────────────────┼───────────────────────────────────────────────┤
  │  N8  │ Schema drift MySQL vs    │ `ALTER TABLE ADD COLUMN` avec type extrait    │
  │      │ Snowflake                │ de MySQL `information_schema.columns`         │
  │      │                          │ (colonnes supprimées ou type changé → humain) │
  └──────┴──────────────────────────┴───────────────────────────────────────────────┘

### Comportement et codes de sortie

  ┌─────────────────────────────────┬───────────────────────────────────┬──────┬──────────────────────────────────────────────┐
  │ Situation                       │ Flag créé                         │ Exit │ Conséquence `batch_loop.sh`                  │
  ├─────────────────────────────────┼───────────────────────────────────┼──────┼──────────────────────────────────────────────┤
  │ 14/14 OK (après fix éventuel)   │ `/tmp/pre_night_ok`               │  0   │ Nuit autorisée normalement                   │
  ├─────────────────────────────────┼───────────────────────────────────┼──────┼──────────────────────────────────────────────┤
  │ Fail non-fixé résiduel          │ (aucun)                           │  1   │ **Nuit skippée** + alerte Teams critique     │
  ├─────────────────────────────────┼───────────────────────────────────┼──────┼──────────────────────────────────────────────┤
  │ `.env` corrigé (N3 fix)         │ `/tmp/pre_night_restart_required` │  2   │ **Nuit skippée** + alerte "restart requis"   │
  └─────────────────────────────────┴───────────────────────────────────┴──────┴──────────────────────────────────────────────┘

Le flag `/tmp/pre_night_ok` est **obligatoire** pour que CDC pré-reload et ref_reload se déclenchent. Sans lui, `batch_loop.sh` skippe ces phases.

### Fallback après restart conteneur

Si le conteneur redémarre en fin de journée (ex: mise à jour Docker), `/tmp` est vidé et `pre_night_ok` disparaît. `batch_loop.sh` détecte ce cas et relance automatiquement `pre_night_healthcheck --fix` au premier cycle nuit, sans attendre le lendemain.

[↑ Retour au sommaire](#table-des-matières)

---

## Niveaux 2a et 2b — Post-checks inline

Ces post-checks sont intégrés directement dans `batch_loop.sh` (pas de script externe). Ils valident que chaque phase critique a effectivement produit le résultat attendu, pas seulement qu'elle s'est terminée sans exception.

### Niveau 2a — Post-check CDC pré-reload (non bloquant)

Exécuté après `run_cdc()` en mode nuit (~21h35 FR).

Vérifie :
- Flag `/tmp/night_cdc_done` créé par `run_cdc()`
- Lag Kafka total `< KAFKA_LAG_THRESHOLD` (défaut 10000)

Si KO : alerte Teams **warning** (non bloquant). La phase suivante (audit purge, backup Metabase, ref_reload) continue.

**Cas capté** : consumer CDC bloqué en boucle de fallback row-by-row (scénario vécu le 19 avril 2026 — 14h de boucle infinie sur un SQL error).

### Niveau 2b — Post-check ref_reload (BLOQUANT)

Exécuté après `bulk_load.py --ref-only --truncate` (~03h30 FR).

Vérifie :
- Les 14 tables référence non vides (`SELECT COUNT(*) FROM RAW_<TABLE>`)
- Aucune table `_BACKUP` résiduelle (CLONE+SWAP nettoyé)

Si KO : alerte Teams **critique** + **`REF_DONE_FLAG` non créé** → `dbt post-reload` skippé au prochain cycle → aucune transformation sur des données incohérentes.

**Cas capté** : bulk_load exit 0 mais une ou plusieurs tables à 0 lignes (CLONE+SWAP a rollback mais flag créé malgré tout), ou `_BACKUP` orphelin dû à un crash entre CLONE et DROP.

Gain : **~11 min de compute économisé** si le ref_reload a échoué (dbt ne tourne pas sur du vide).

[↑ Retour au sommaire](#table-des-matières)

---

## Niveau 3 — Pipeline maintenance post-exécution

```bash
python scripts/pipeline_maintenance.py --fix-safe
```

Ce script orchestre les **4 phases d'audit post-exécution** du pipeline MediCore. Il s'auto-authentifie via `.env`, détecte et corrige les problèmes automatiquement. Il tourne chaque nuit à **04h30 FR** (02h30 UTC) dans `batch_loop.sh`, après le ref_reload, le dbt post-reload et les post-checks 2a/2b.

**Phase 1 Healthcheck retirée** — les 7 checks H1-H7 ont été déplacés dans le Niveau 1 (pre-night) à 20h30 FR, pour un contrôle **avant** la nuit plutôt qu'après.

Autres modes d'exécution :

```bash
# Simulation : détecte sans corriger
python scripts/pipeline_maintenance.py --dry-run

# Tous les fix (y compris reloads lourds) — mode manuel
python scripts/pipeline_maintenance.py --fix

# Une seule phase
python scripts/pipeline_maintenance.py --phase cdc
python scripts/pipeline_maintenance.py --phase bulk
python scripts/pipeline_maintenance.py --phase dbt
python scripts/pipeline_maintenance.py --phase metabase
```

[↑ Retour au sommaire](#table-des-matières)

---

### Architecture de l'orchestrateur

```
scripts/pipeline_maintenance.py (orchestrateur Niveau 3)
  │
  ├── S'auto-authentifie (Snowflake + Metabase + Kafka via .env)
  │
  ├── Phase 2 : cdc_maintenance.py (C1-C6)
  │                C4 redondant avec pre-night H6 — conservé en défense en profondeur
  │
  ├── Phase 3 : bulk_maintenance.py (B1-B6)
  │                B6 redondant avec pre-night N8 — conservé en défense en profondeur
  │
  ├── Phase 4 : dbt_maintenance.py (D1-D6)
  │                parse target/run_results.json généré par dbt post-reload
  │
  ├── Phase 5 : metabase_maintenance.py (P1-P10)
  │                P10 appelle provision_rls.py pour les nouvelles pharmacies
  │
  ├── Hook final : cost_monitoring.py (audit coût Snowflake)
  │
  └── Rapport global (OK / FAIL / WARN / SKIP par phase)
```

Chaque script reste utilisable individuellement pour le dépannage ponctuel. L'orchestrateur les appelle en séquence et gère les timeouts par phase.

[↑ Retour au sommaire](#table-des-matières)

---

## Les 4 phases

### Phase 1 — Healthcheck (déplacée vers Niveau 1 pre-night)

Les 7 checks d'infrastructure (H1-H7) tournaient autrefois à 04h30 FR après la nuit. Ils sont maintenant exécutés par `pre_night_healthcheck.py` à **20h30 FR**, avant la nuit. Voir [Niveau 1 — Pre-night healthcheck](#niveau-1--pre-night-healthcheck).

Détails conservés ici pour référence :

  ┌─────┬──────────────────────────────────┬─────────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction --fix-safe                               │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H1  │ MySQL RDS inaccessible           │ Alerte (infrastructure AWS)                         │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H2  │ Kafka broker down                │ Restart Kafka + Zookeeper (sauf si logs "corrupt")  │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H3  │ Snowflake inaccessible           │ Resume warehouse + vérification credits             │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H4  │ Warehouse suspendu               │ Resume automatique                                  │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H5  │ Metabase API inaccessible        │ Alerte                                              │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H6  │ Debezium connector FAILED        │ Restart automatique                                 │
  ├─────┼──────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ H7  │ Permissions Snowflake insuffisantes │ Alerte                                           │
  └─────┴──────────────────────────────────┴─────────────────────────────────────────────────────┘

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
  │ B1  │ Lock file périmé                 │ --fix-safe : suppression automatique              │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B2  │ Tables RAW vides                 │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B3  │ Doublons tables référence        │ Alerte                                            │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B4  │ Réconciliation MySQL/Snowflake   │ --fix uniquement : CLONE+SWAP par table           │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B5  │ Données périmées (> 48h)         │ --fix uniquement : CLONE+SWAP 14 tables           │
  │     │                                  │ --fix-safe : alerte (rechargement par batch_loop) │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ B6  │ Schema drift MySQL/Snowflake     │ --fix-safe : ALTER TABLE avec type détecté MySQL  │
  └─────┴──────────────────────────────────┴───────────────────────────────────────────────────┘

**Script** : `scripts/bulk_maintenance.py`
**Pattern CLONE+SWAP** : backup zero-copy avant TRUNCATE, rollback instantané si échec.

### Phase 4 — dbt (Staging / MARTS)

Vérifie l'état des modèles et tests dbt.

  ┌─────┬──────────────────────────────────┬───────────────────────────────────────────────────┐
  │  #  │ Problème                         │ Correction                                        │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D1  │ Modèles dbt en erreur            │ --fix uniquement : relance dbt run+test           │
  │     │                                  │ --fix-safe : alerte                               │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D2  │ Tests dbt échoués                │ --fix uniquement : relance dbt run+test           │
  │     │                                  │ (1 seul retry/jour, flag anti-boucle)             │
  ├─────┼──────────────────────────────────┼───────────────────────────────────────────────────┤
  │ D3  │ Source freshness dépassée        │ --fix-safe : relance dbt source freshness         │
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

Chronologie nocturne type **en mode incremental** (mardi→samedi). Les variantes dimanche/lundi sont décrites dans la sous-section suivante.

  ┌──────────────┬──────────────────────────────────────────┬─────────────────────────────────────────────────────────┐
  │ Heure FR     │ Phase                                    │ Détail                                                  │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 20h30        │ ★ NIVEAU 1 — Pre-night healthcheck ★    │ `pre_night_healthcheck.py --fix` : H1-H7 + N2-N8.       │
  │              │                                          │ Auto-fix H2/H3/H4/H6/N2/N3/N5/N6/N7/N8.                 │
  │              │                                          │ Si OK → `/tmp/pre_night_ok`.                            │
  │              │                                          │ Sinon → alerte Teams + nuit skippée.                    │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 21h00        │ Passage en mode nuit                     │ Reset flags quotidiens (REF_DONE, NIGHT_CDC_DONE,       │
  │              │                                          │ POST_RELOAD_DBT_DONE, MB_PROV_DONE).                    │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 21h30        │ CDC pré-reload                           │ Flush backlog Kafka avant ref_reload                    │
  │              │                                          │ [guard `pre_night_ok`].                                 │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 21h35        │ ★ NIVEAU 2a — Post-check CDC (inline) ★ │ Vérifie flag + lag Kafka acceptable.                    │
  │              │                                          │ Warning Teams si KO (non bloquant).                     │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 22h00        │ Audit purge + Backup Metabase            │ `DELETE AUDIT > 90j` +                                  │
  │              │                                          │ `pg_dump` PostgreSQL Metabase.                          │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 23h00        │ ref_reload INCREMENTAL 30j               │ 4 tables fenêtre glissante :                            │
  │ → 23h16      │                                          │   MEDIPRIX_FACTURES ~5 min, STOCKHISTORY ~3 min,        │
  │              │                                          │   DAYBYDAY ~1 min, MANQHISTORY ~10 s.                   │
  │              │                                          │ + TRUNCATE sur 10 petites tables (~7 min).              │
  │              │                                          │ Total ~16 min [guard `pre_night_ok`].                   │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ ~23h16       │ ★ NIVEAU 2b — Post-check ref_reload ★   │ Vérifie 14 tables non vides + 0 `_BACKUP` résiduel.     │
  │              │                                          │ Si KO : `REF_DONE_FLAG` non créé                        │
  │              │                                          │ → dbt skippé + alerte Teams critique.                   │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ ~23h26       │ dbt post-reload                          │ Conditionné `REF_DONE_FLAG` (cycle +10 min).            │
  │ → 23h37      │                                          │ CDC flush + staging (1m40) + marts (8m35) +             │
  │              │                                          │ tests (47s) + source freshness (3s).                    │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ ~23h47       │ ★ NIVEAU 3 — pipeline_maintenance ★     │ `pipeline_maintenance.py --fix-safe` :                  │
  │ → 23h57      │                                          │   Phase 2 CDC (C1-C6),                                  │
  │              │                                          │   Phase 3 Bulk (B1-B6),                                 │
  │              │                                          │   Phase 4 dbt (D1-D6),                                  │
  │              │                                          │   Phase 5 Metabase (P1-P10 + provisionnement).          │
  │              │                                          │ Hook cost_monitoring.                                   │
  │              │                                          │ Rapport Teams consultable dès 23h57 FR.                 │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 00h00 → 07h00│ Mode nuit sleep (~7h)                    │ Aucune activité batch_loop.                             │
  │              │                                          │ Kafka/Debezium accumulent les events qui seront         │
  │              │                                          │ traités au passage en mode jour.                        │
  ├──────────────┼──────────────────────────────────────────┼─────────────────────────────────────────────────────────┤
  │ 07h00        │ Passage en mode jour                     │ CDC reprend (10 min dev, 10 min prod).                  │
  │              │                                          │ dbt toutes les 3 (dev) / 6 (prod) itérations CDC.       │
  └──────────────┴──────────────────────────────────────────┴─────────────────────────────────────────────────────────┘
  
### Variantes selon le jour de la semaine

- **Dimanche (DOW=0)** : ref_reload SKIP, les flags sont créés directement (dbt et pipeline_maintenance tournent quand même pour les CDC tables et les tests).
- **Lundi (DOW=1)** : ref_reload FULL (~4h48). Fin ref_reload vers 03h48 FR, post-check 2b à ~03h48, dbt post-reload vers ~04h00, pipeline_maintenance vers ~04h20. Rapport Teams vers ~04h30.
- **Mardi→Samedi (DOW=2..6)** : ref_reload INCREMENTAL (~16 min) comme détaillé ci-dessus.

**Guard `pre_night_ok`** : CDC pré-reload et ref_reload ne se déclenchent que si `/tmp/pre_night_ok` est présent. Sans lui, les phases sont skippées et le batch_loop logge "phase skippée — pre_night_ok absent". Cela empêche de lancer des phases coûteuses sur une infra dégradée.

**Fenêtre ref_reload** : la fonction `is_ref_reload_window()` gère le wrap minuit (21h-02h UTC). Elle retourne vrai si `REF_RELOAD_HOUR <= HOUR < POST_RELOAD_DBT_HOUR`, avec support de l'enjambement minuit (ex: 21h-02h → vrai si HOUR >= 21 OU HOUR < 2).

**Pattern CLONE+SWAP** : `bulk_load.py` crée un backup zero-copy avant TRUNCATE. Si le reload échoue ou charge 0 ligne, le backup est SWAP en place (rollback). Sinon, il est DROP (cleanup).

**Flags et dépendances** :

  ┌────────────────────────────────────────┬──────────────────────────┬─────────────────────────────┬──────────────────────────────┐
  │ Flag                                   │ Créé par                 │ Consommé par                │ Reset                        │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/pre_night_ok`                    │ Niveau 1 (20h30)         │ CDC pré-reload, ref_reload  │ Début pre-night suivant      │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/pre_night_restart_required`      │ Niveau 1 N3 fix          │ Opérateur humain            │ Au restart conteneur         │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/pre_night_done_today`            │ Niveau 1                 │ Évite re-run même jour      │ 14h UTC lendemain            │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/night_cdc_done`                  │ CDC pré-reload           │ (empêche re-run)            │ 19h UTC lendemain            │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/ref_bulk_done_today`             │ ref_reload + Niveau 2b   │ dbt post-reload             │ 19h UTC lendemain            │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/post_reload_dbt_done`            │ dbt post-reload          │ pipeline_maintenance        │ 19h UTC lendemain            │
  ├────────────────────────────────────────┼──────────────────────────┼─────────────────────────────┼──────────────────────────────┤
  │ `/tmp/mb_provision_done_today`         │ pipeline_maintenance     │ (empêche re-run)            │ 05h UTC même jour            │
  └────────────────────────────────────────┴──────────────────────────┴─────────────────────────────┴──────────────────────────────┘

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
3. Lancer le pre-night healthcheck avec auto-fix :
   docker exec -it medicore_elt_batch python //app/scripts/pre_night_healthcheck.py --fix
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
  │ healthcheck_maintenance.py          │ Connectivité MySQL, Kafka, Snowflake, Metabase,  │ python scripts/healthcheck_maintenance.py        │
  │                                     │ Debezium, permissions                            │ [--fix-safe] [--fix]                             │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ cdc_maintenance.py                  │ Lag Kafka, DLQ, doublons CDC, Debezium, offsets  │ python scripts/cdc_maintenance.py                │
  │                                     │                                                  │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ bulk_maintenance.py                 │ Lock, tables vides, doublons, réconciliation,    │ python scripts/bulk_maintenance.py               │
  │                                     │ timestamps, schema drift                         │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ dbt_maintenance.py                  │ Modèles en erreur, tests échoués, freshness,     │ python scripts/dbt_maintenance.py                │
  │                                     │ tables MARTS vides                               │ [--fix-safe] [--fix] [--dry-run]                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ metabase_maintenance.py             │ P1-P10 (cartes, filtres, embedding,              │ python scripts/metabase_maintenance.py           │
  │                                     │ provisionnement pharmacies)                      │ [--dry-run] [--diagnose --card/--dashboard]      │
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
  │     │                             │ avant restart. Si corrompu → intervention manuelle.                 │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H3  │ Snowflake inaccessible      │ Resume warehouse + vérification credits. Si credits épuisés →       │
  │     │                             │ alerte sans fix.                                                    │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H4  │ Warehouse suspendu          │ Resume automatique (auto-suspend normal, pas une erreur).           │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H5  │ Metabase API inaccessible   │ Vérifier que le conteneur Metabase tourne : docker compose ps       │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ H6  │ Debezium connector FAILED   │ Restart automatique. Cause fréquente : KafkaSchemaHistory           │
  │     │                             │ ThreadPoolExecutor terminé (problème connu Debezium).               │
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
  │ B3  │ Doublons tables référence   │ Détecte via GROUP BY ... HAVING COUNT > 1 sur les 14 tables ref.    │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B4  │ Réconciliation MySQL/SF     │ Compare COUNT MySQL vs Snowflake sur 5 tables principales.          │
  │     │                             │ --fix : CLONE+SWAP par table (backup zero-copy, rollback si échec). │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B5  │ Données périmées            │ CDC_TIMESTAMP > 48h sur les tables RAW.                             │
  │     │                             │ --fix : CLONE+SWAP 14 tables ref (table par table, rollback auto).  │
  │     │                             │ --fix-safe : alerte (rechargement par batch_loop.sh 01h00).         │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ B6  │ Schema drift MySQL/SF       │ Colonnes ajoutées/supprimées dans MySQL pas reflétées dans          │
  │     │                             │ Snowflake. Fix : ALTER TABLE ADD COLUMN avec type détecté MySQL.    │
  └─────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘

### Phase 4 — dbt (D1-D6)

  ┌─────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┐
  │  #  │ Problème                    │ Détail                                                              │
  ├─────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
  │ D1  │ Modèles dbt en erreur       │ Parse run_results.json. Affiche le modèle + message d'erreur.       │
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
