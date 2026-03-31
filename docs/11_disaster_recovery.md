# Plan de Disaster Recovery — MediCore

## Table des matières

1. [Objectif](#objectif)
2. [Inventaire des actifs](#inventaire-des-actifs)
3. [Mesures préventives en place](#mesures-préventives-en-place)
4. [Scénarios de sinistre et procédures](#scénarios-de-sinistre-et-procédures)
   - [S1 — Perte du serveur Docker](#s1--perte-du-serveur-docker)
   - [S2 — DROP DATABASE MEDICORE_PROD](#s2--drop-database-medicore_prod)
   - [S3 — Credentials compromises](#s3--credentials-compromises)
   - [S4 — Perte du compte Snowflake](#s4--perte-du-compte-snowflake)
   - [S5 — Corruption des données RAW](#s5--corruption-des-données-raw)
   - [S6 — Perte du repository GitHub](#s6--perte-du-repository-github)
   - [S7 — Perte des dashboards Metabase](#s7--perte-des-dashboards-metabase)
5. [Procédure de restauration Metabase](#procédure-de-restauration-metabase)
6. [Matrice de décision](#matrice-de-décision)
7. [Contacts et escalade](#contacts-et-escalade)

---

## Objectif

Documenter les procédures de reprise d'activité pour le pipeline MediCore.
Ce plan couvre les sinistres majeurs (perte de serveur, de données, de credentials)
et les procédures de restauration associées.

**Objectifs de reprise** :
- **RTO** (temps de reprise) : < 4h pour les scénarios courants (S1, S5, S7)
- **RPO** (perte de données acceptable) : < 24h (1 jour de Time Travel)

[↑ Retour au sommaire](#table-des-matières)

---

## Inventaire des actifs

  ┌──────────────────────────┬──────────────────────────────┬────────────────────────────────┬─────────────────────────────┐
  │ Actif                    │ Où il vit                    │ Criticité                      │ Protection                  │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Code source              │ GitHub (remote)              │ Haute                          │ Git (distribué) + clone     │
  │ (pipelines, dbt, scripts)│ + clone local                │                                │ local sur la machine        │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Données Snowflake        │ Snowflake (cloud AWS)        │ Critique — 920M lignes RAW +   │ Time Travel (1 jour) +      │
  │ (RAW, STAGING, MARTS,    │                              │ STAGING + MARTS + AUDIT +      │ Fail-safe (7 jours) +       │
  │ AUDIT, SNAPSHOTS)        │                              │ SNAPSHOTS                      │ MySQL RDS (source)          │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Credentials              │ .env (local) +               │ Critique — sans eux, rien      │ Copie sur clé USB +         │
  │                          │ GitHub Secrets (remote)      │ ne fonctionne                  │ GitHub Secrets (chiffrés)   │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Config Metabase          │ Volume Docker PostgreSQL     │ Moyenne — 16 dashboards,       │ pg_dump quotidien           │
  │ (dashboards, users,      │ (metabase_data)              │ 98 cards, comptes users        │ (backups/metabase/)         │
  │ collections)             │                              │                                │ rétention 30 jours          │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Config Debezium          │ Kafka Connect (mémoire)      │ Basse                          │ Recréé par setup.sh         │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ Offsets Kafka            │ Kafka interne                │ Moyenne — perte = re-consomme  │ Volume Docker               │
  │                          │ (__consumer_offsets)         │ des messages déjà traités      │ (connect_offset)            │
  ├──────────────────────────┼──────────────────────────────┼────────────────────────────────┼─────────────────────────────┤
  │ DDL Snowflake            │ scripts/DDL_WH.sql +         │ Basse                          │ Versionné dans Git          │
  │                          │ DDL_TABLES.sql               │                                │                             │
  └──────────────────────────┴──────────────────────────────┴────────────────────────────────┴─────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Mesures préventives en place

  ┌────┬──────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ #  │ Mesure                           │ Détail                                                   │
  ├────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ A1 │ Backup credentials               │ .env copié sur clé USB externe                           │
  ├────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ A2 │ Snowflake Time Travel + Fail-safe│ Time Travel 1 jour (self-service) + Fail-safe 7 jours    │
  │    │                                  │ (via support Snowflake). Total : 8 jours pour réagir.    │
  ├────┼──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ A3 │ Backup Metabase (pg_dump)        │ Dump quotidien automatique à 00h (batch_loop.sh).        │
  │    │                                  │ Fichiers dans backups/metabase/ (rétention 30 jours).    │
  │    │                                  │ Restauration via scripts/restore_metabase.sh.            │
  └────┴──────────────────────────────────┴──────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Scénarios de sinistre et procédures

### S1 — Perte du serveur Docker

**Cause** : disque HS, VM supprimée, machine volée.

**Impact** : pipeline arrêté, dashboards Metabase inaccessibles. Données Snowflake intactes (cloud).

**Procédure de reprise** :

```
1. Installer les prérequis sur la nouvelle machine
   (voir README.md §Prérequis : Docker, SnowSQL, jq)

2. Cloner le code
   git clone https://github.com/auganmadet/MediCore.git
   cd MediCore

3. Restaurer le .env
   Copier le .env depuis la clé USB de backup

4. Lancer le setup complet
   bash scripts/setup.sh --with-snowflake-ddl

5. Restaurer Metabase (si backup disponible)
   Copier le dernier fichier backups/metabase/metabase_*.sql.gz
   depuis la clé USB ou un autre backup
   Voir §Procédure de restauration Metabase ci-dessous

6. Vérifier
   bash scripts/verify_setup.sh
```

**RTO** : ~2-4h (dont 45-90 min de bulk load initial).

**RPO** : 0 (données Snowflake intactes). Perte des dashboards Metabase si pas de backup pg_dump.

[↑ Retour au sommaire](#table-des-matières)

---

### S2 — DROP DATABASE MEDICORE_PROD

**Cause** : erreur humaine ou attaque.

**Procédure de reprise** :

```
Cas 1 : moins de 24h (Time Travel actif)
─────────────────────────────────────────
   UNDROP DATABASE MEDICORE_PROD;
   -- C'est tout. La base est restaurée instantanément.

Cas 2 : entre 1 et 8 jours (Fail-safe)
─────────────────────────────────────────
   1. Ouvrir un ticket au support Snowflake
   2. Demander la restauration de MEDICORE_PROD
   3. Attendre (quelques heures à 1 jour)

Cas 3 : plus de 8 jours (données perdues)
─────────────────────────────────────────
   1. Recréer la base
      snowsql -c medicore_admin -f scripts/DDL_WH.sql
      snowsql -c medicore_admin -f scripts/DDL_TABLES.sql

   2. Re-bulk load complet depuis MySQL RDS
      docker exec -it medicore_elt_batch python /app/pipelines/bulk_load.py

   3. Relancer dbt
      docker exec -it medicore_elt_batch bash -c "cd /app/dbt && dbt run --target prod"

   Perte : toutes les données AUDIT et SNAPSHOTS SCD2.
```

**RTO** : instantané (cas 1), quelques heures (cas 2), 2-4h (cas 3).

[↑ Retour au sommaire](#table-des-matières)

---

### S3 — Credentials compromises

**Cause** : credentials exposées dans un log, un commit Git, un screenshot, un email.

**Procédure de reprise** :

```
1. Rotation immédiate de TOUS les credentials exposés
   Suivre docs/09_rotation_credentials.md

2. Auditer les accès Snowflake
   SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE USER_NAME = '<user_compromis>'
   ORDER BY START_TIME DESC
   LIMIT 100;

3. Vérifier qu'aucune action destructrice n'a été exécutée
   Chercher : DROP, DELETE, TRUNCATE, ALTER, GRANT

4. Si des données ont été supprimées → voir S2

5. Mettre à jour le .env et les GitHub Secrets
   avec les nouveaux credentials

6. Redémarrer le pipeline
   docker compose restart medicore-elt-batch
```

**RTO** : 30 min à 1h.

[↑ Retour au sommaire](#table-des-matières)

---

### S4 — Perte du compte Snowflake

**Cause** : suspension pour impayé, suppression accidentelle, problème Snowflake.

**Procédure de reprise** :

```
1. Contacter le support Snowflake
   support.snowflake.com

2. Si le compte est récupérable : rien d'autre à faire

3. Si le compte est perdu :
   a. Créer un nouveau compte Snowflake
   b. Mettre à jour .env et GitHub Secrets (nouveau SNOWFLAKE_ACCOUNT)
   c. Exécuter les DDL
      snowsql -c medicore_admin -f scripts/DDL_WH.sql
      snowsql -c medicore_admin -f scripts/DDL_TABLES.sql
   d. Re-bulk load complet depuis MySQL RDS
   e. Relancer dbt

   Perte irréversible : historique AUDIT + SNAPSHOTS SCD2.
```

**RTO** : variable (dépend du support Snowflake). Jusqu'à plusieurs jours.

[↑ Retour au sommaire](#table-des-matières)

---

### S5 — Corruption des données RAW

**Cause** : full-refresh buggé, mauvais bulk load, bug dans le consumer CDC.

**Procédure de reprise** :

```
Option A : Time Travel (< 24h)
──────────────────────────────
   Voir docs/08_procedure_rollback.md pour la procédure détaillée
   avec Time Travel (restauration table par table).

Option B : Re-bulk load des tables affectées
─────────────────────────────────────────────
   docker exec -it medicore_elt_batch python /app/pipelines/bulk_load.py \
     --tables RAW_COMMANDES,RAW_FACTURES --truncate

   Puis relancer dbt staging + marts sur les tables concernées.
```

**RTO** : 5 min (Time Travel) à 2h (re-bulk load partiel).

[↑ Retour au sommaire](#table-des-matières)

---

### S6 — Perte du repository GitHub

**Cause** : suppression accidentelle du repo, compte GitHub compromis.

**Procédure de reprise** :

```
1. Le clone local contient tout l'historique Git
   cd /c/Temp/MediCore
   git log  # vérifier que l'historique est complet

2. Recréer le repo sur GitHub
   gh repo create auganmadet/MediCore --private --source=. --push

3. Reconfigurer GitHub Secrets (5 secrets Snowflake)
   Voir docs/02_workflow_multi_env.md §GitHub Secrets

4. Reconfigurer Branch Protection sur main
   Voir docs/02_workflow_multi_env.md §Branch protection
```

**RTO** : 30 min.

[↑ Retour au sommaire](#table-des-matières)

---

### S7 — Perte des dashboards Metabase

**Cause** : volume Docker corrompu, `docker volume rm` accidentel, migration Metabase ratée.

**Procédure de reprise** :

```
Option A : Restaurer depuis un backup pg_dump (5 min)
─────────────────────────────────────────────────────
   Voir §Procédure de restauration Metabase ci-dessous.

Option B : Recréer manuellement (plusieurs heures)
───────────────────────────────────────────────────
   Suivre docs/06_Dashboards.md pour recréer les 98 cards
   et 16 dashboards. Long mais documenté.
```

**RTO** : 5 min (option A) à plusieurs heures (option B).

[↑ Retour au sommaire](#table-des-matières)

---

## Procédure de restauration Metabase

### Prérequis

- Un fichier backup `backups/metabase/metabase_*.sql.gz`
- Les conteneurs `metabase_db` et `medicore_elt_batch` en cours d'exécution

### Étapes

```bash
# 1. Arrêter Metabase (pour éviter les écritures pendant la restauration)
docker compose stop metabase

# 2. Restaurer depuis le conteneur ELT
docker exec -it medicore_elt_batch bash /app/scripts/restore_metabase.sh
# Sans argument : restaure le backup le plus récent
# Avec argument : docker exec -it medicore_elt_batch bash /app/scripts/restore_metabase.sh /app/backups/metabase/metabase_2026-03-30_0000.sql.gz

# 3. Redémarrer Metabase
docker compose start metabase

# 4. Vérifier (attendre ~30s que Metabase redémarre)
# Ouvrir http://localhost:3000 et vérifier que les dashboards sont présents
```

### Backup manuel (hors cycle automatique)

```bash
docker exec medicore_elt_batch bash /app/scripts/backup_metabase.sh
```

Les backups sont dans `backups/metabase/` avec rétention automatique de 30 jours.

[↑ Retour au sommaire](#table-des-matières)

---

## Matrice de décision

  ┌──────────────────────────────────┬──────────┬──────────────────────────────────────────────────┐
  │ Symptôme                         │ Scénario │ Première action                                  │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Pipeline arrêté, Snowflake OK    │ S1       │ Vérifier Docker, redémarrer ou re-setup          │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Database MEDICORE_PROD absente   │ S2       │ UNDROP DATABASE si < 24h                         │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Credentials refusées             │ S3       │ Vérifier .env, rotation si compromises           │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Compte Snowflake inaccessible    │ S4       │ Contacter support Snowflake                      │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Données incohérentes dans MARTS  │ S5       │ Time Travel sur RAW + re-run dbt                 │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Repo GitHub absent               │ S6       │ Re-push depuis le clone local                    │
  ├──────────────────────────────────┼──────────┼──────────────────────────────────────────────────┤
  │ Dashboards Metabase vides        │ S7       │ Restaurer pg_dump                                │
  └──────────────────────────────────┴──────────┴──────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Contacts et escalade

  ┌────────────────────────┬──────────────────────────────────────────────────────┐
  │ Sujet                  │ Contact                                              │
  ├────────────────────────┼──────────────────────────────────────────────────────┤
  │ Support Snowflake      │ support.snowflake.com (ticket en ligne)              │
  ├────────────────────────┼──────────────────────────────────────────────────────┤
  │ Support GitHub         │ support.github.com                                   │
  ├────────────────────────┼──────────────────────────────────────────────────────┤
  │ Hébergeur Docker       │ Machine locale (pas de support externe)              │
  ├────────────────────────┼──────────────────────────────────────────────────────┤
  │ MySQL RDS (source)     │ Administrateur AWS du compte WinStat                 │
  └────────────────────────┴──────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Voir aussi

- [Procédure de rollback](08_procedure_rollback.md) — restauration Time Travel (cas courant)
- [Rotation des credentials](09_rotation_credentials.md) — procédure de rotation trimestrielle
- [Workflow multi-environnement](02_workflow_multi_env.md) — GitHub Secrets et Branch Protection
- [Opérations](03_operations.md) — exploitation quotidienne et monitoring
