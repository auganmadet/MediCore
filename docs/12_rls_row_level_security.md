# Row-Level Security (RLS) — MediCore

## Table des matières

1. [Objectif](#objectif)
2. [Contraintes](#contraintes)
3. [Architecture retenue](#architecture-retenue)
   - [Siège — Metabase (existant)](#siège--metabase-existant)
   - [Pharmaciens — Superset (à déployer)](#pharmaciens--superset-à-déployer)
4. [Profils d'accès](#profils-daccès)
5. [Provisionnement Metabase (Siège)](#provisionnement-metabase-siège)
   - [Organisation des collections](#organisation-des-collections)
   - [Permissions par groupe](#permissions-par-groupe)
   - [Script provision_rls.py](#script-provision_rlspy)
6. [Provisionnement Superset (Pharmaciens)](#provisionnement-superset-pharmaciens)
   - [RLS natif Superset](#rls-natif-superset)
   - [Workflow automatisé](#workflow-automatisé)
7. [Relation pharmacien-pharmacie](#relation-pharmacien-pharmacie)
8. [Approches testées et abandonnées](#approches-testées-et-abandonnées)
9. [Limites et points de vigilance](#limites-et-points-de-vigilance)
10. [Fichiers impactés](#fichiers-impactés)
11. [Dépannage](#dépannage)

---

## Objectif

Permettre à chaque pharmacien de ne voir **que les données de sa pharmacie** dans les dashboards BI, sans surcoût logiciel, avec un provisionnement automatisé.

[↑ Retour au sommaire](#table-des-matières)

---

## Contraintes

  ┌────┬────────────────────────────────────────────────────────────────────────┐
  │ #  │ Contrainte                                                             │
  ├────┼────────────────────────────────────────────────────────────────────────┤
  │ C1 │ Metabase OSS — pas de sandboxing natif, pas de dashboards read-only    │
  ├────┼────────────────────────────────────────────────────────────────────────┤
  │ C2 │ Les pharmaciens n'ont pas accès à Snowflake (uniquement BI)            │
  ├────┼────────────────────────────────────────────────────────────────────────┤
  │ C3 │ Pas de surcoût logiciel — outils open source uniquement                │
  ├────┼────────────────────────────────────────────────────────────────────────┤
  │ C4 │ Relation pharmacien-pharmacie N:N (titulaire multi-pharmacies)         │
  ├────┼────────────────────────────────────────────────────────────────────────┤
  │ C5 │ Automatisation maximale — intervention humaine minimale                │
  └────┴────────────────────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Architecture retenue

Deux outils BI en parallèle, chacun pour un public différent :

```
  Snowflake MEDICORE_PROD.MARTS (source unique)
       │
       ├── Metabase (port 3000) → Siège (Admin, IT, Marketing, RH, Achats)
       │     1 connexion : MEDICORE_ANALYST
       │     16 dashboards partagés
       │     Pas de RLS (tout le Siège voit tout)
       │
       └── Superset (port 8088) → Pharmaciens (268 pharmacies)
             1 connexion : MEDICORE_ANALYST
             16 dashboards partagés (recréés)
             RLS natif par rôle (filtre automatique par pharmacie)
```

### Siège — Metabase (existant)

Le Siège continue d'utiliser Metabase. Tous les utilisateurs partagent la même connexion `MEDICORE_ANALYST` et voient les mêmes 16 dashboards. Le filtrage par domaine (Marketing ne voit que Ventes, etc.) est assuré par les permissions de collections Metabase.

### Pharmaciens — Superset (à déployer)

Les pharmaciens utilisent Apache Superset avec RLS natif. Chaque pharmacie a un rôle Superset avec une règle RLS qui filtre automatiquement `pharmacie_sk`. Les 16 dashboards sont partagés — pas de copie, pas de multi-connexion. Le pharmacien ne peut pas contourner le filtre ni modifier les dashboards.

[↑ Retour au sommaire](#table-des-matières)

---

## Profils d'accès

  ┌─────────────────────┬──────────┬─────────────────────────────────────────────────┐
  │ Profil              │ Outil    │ Permissions                                     │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ Admin (vous)        │ Metabase │ Tout                                            │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ IT                  │ Metabase │ Vue Admin + curate IT/                          │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ Marketing           │ Metabase │ Vue Ventes + curate Marketing/                  │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ RH                  │ Metabase │ Vue Qualité + curate RH/                        │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ Achats              │ Metabase │ Vue Achats + curate Achats/                     │
  ├─────────────────────┼──────────┼─────────────────────────────────────────────────┤
  │ Pharmacien          │ Superset │ Vue 16 dashboards, RLS filtre sa pharmacie      │
  │                     │          │ Curate dans son espace, SQL natif bloqué        │
  └─────────────────────┴──────────┴─────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Provisionnement Metabase (Siège)

### Organisation des collections

```
MediCore BI/
│
├── Direction Générale/                 D1, D2, D3
│   ├── Cards/Admin/
│   ├── Dashboards/Admin/
│   ├── Cards/<Service>/
│   └── Dashboards/<Service>/
├── Ventes & Performance/               D4, D5, D6
├── Achats & Stock/                     D7, D8, D9, D10, D11
├── Qualité & Pilotage/                 D12, D13, D14
└── Détail opérationnel/                D15, D16
```

### Permissions par groupe

  ┌──────────────────────────────────────┬─────────┬─────────────────────────────────────────────┐
  │ Ressource                            │ Droit   │ Détail                                      │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Données MediCore                     │ query   │ Query builder uniquement, SQL natif bloqué  │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Collections Admin                    │ vue     │ Voir, filtrer, exporter                     │
  ├──────────────────────────────────────┼─────────┼─────────────────────────────────────────────┤
  │ Collection service (IT/, Achats/...) │ curate  │ Créer, modifier ses propres cartes          │
  └──────────────────────────────────────┴─────────┴─────────────────────────────────────────────┘

> **Limitation Metabase OSS** : la permission "Vue" sur les collections permet aussi de modifier les dashboards. C'est une limitation connue de Metabase OSS (pas de distinction lecture/écriture sur les dashboards). Les dashboards modifiés accidentellement sont restaurables via l'historique Metabase.

### Script provision_rls.py

Le script détecte les nouvelles pharmacies dans `dim_pharmacie` et crée les groupes/collections Metabase. En mode Alternative A (pas de multi-connexion), il crée uniquement :
- 1 groupe Metabase par pharmacie
- 1 collection par pharmacie sous `Pharmacies/` (curate)
- Permissions : Vue sur MediCore BI, query-builder uniquement

```bash
# Provisionnement automatique (batch_loop.sh a 04h30 FR)
python scripts/provision_rls.py --run-id <UUID>

# Provisionnement ciblé
python scripts/provision_rls.py --run-id <UUID> --pha-id 217

# Simulation
python scripts/provision_rls.py --run-id <UUID> --dry-run
```

[↑ Retour au sommaire](#table-des-matières)

---

## Provisionnement Superset (Pharmaciens)

### RLS natif Superset

Apache Superset inclut le Row-Level Security dans sa version open source. Pour chaque pharmacie :

```sql
-- Règle RLS dans Superset (pas dans Snowflake)
-- Table : mart_kpi_synthese_pharmacie
-- Rôle : Pharmacie du Soleil
-- Clause : pharmacie_sk = 'a5bfc9e07964f8dddeb95fc584cd965d'
```

Superset ajoute automatiquement ce `WHERE` à chaque requête du pharmacien. Le pharmacien ne peut pas le contourner.

### Workflow provisionnement (Metabase -- a la demande)

Le provisionnement est **automatique** : `batch_loop.sh` exécute `pipeline_maintenance.py --fix-safe` chaque nuit à 04h30 FR (après le ref_reload et le dbt post-reload qui garantissent que `dim_pharmacie` est à jour).

Le script est **léger** si rien à faire (~2 secondes : 1 SELECT Snowflake + 1 authentification Metabase) et **autonome** (s'auto-authentifie via `.env`, ne dépend d'aucun autre script).

```
NUIT (21h → 07h)
━━━━━━━━━━━━━━━━
00h30  CDC pré-reload
23h00 FR  ref_reload 14 tables référence (CLONE+SWAP, ~4h30)
04h00 FR  CDC + dbt post-reload → dim_pharmacie à jour
04h30 FR  ★ pipeline_maintenance.py --fix-safe ★ (inclut metabase P1-P10)
         → Détecte les nouvelles pharmacies dans dim_pharmacie
         → Ne fait rien si aucune nouvelle (idempotent)
         → Provisionne automatiquement si détection
```

```
metabase_maintenance.py
       │
       ├── S'authentifie à Metabase (lit .env, pas de token manuel)
       ├── S'authentifie à Snowflake (lit .env)
       ├── Détecte les nouvelles pharmacies dans dim_pharmacie
       │   (LEFT JOIN sur AUDIT.RLS_PHARMACY_ACCESS)
       ├── Pour chaque nouvelle pharmacie :
       │   ├── Crée le groupe Metabase
       │   ├── Crée la collection sous Pharmacies/
       │   ├── Configure les permissions (query-builder, curate)
       │   └── INSERT dans AUDIT.RLS_PHARMACY_ACCESS + LOG
       └── Affiche le rapport
```

Lancement manuel possible à tout moment :

```bash
python scripts/metabase_maintenance.py              # toutes les nouvelles
python scripts/metabase_maintenance.py --dry-run     # simulation
python scripts/metabase_maintenance.py --pha-id 217  # une seule pharmacie
```

### Scripts utilitaires (depannage ponctuel)

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Script                              │ Quand l'utiliser                                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ `scripts/fix_cards_db.py`           │ Cartes en erreur (mauvais database_id)           │
  │                                     │ Usage : `python scripts/get_token.py` puis       │
  │                                     │ `python scripts/fix_cards_db.py <token>`         │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ `scripts/enable_embedding.py`       │ Nouveau dashboard a rendre embeddable            │
  │                                     │ Usage : `python scripts/get_token.py` puis       │
  │                                     │ `python scripts/enable_embedding.py <token>`     │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ `scripts/check_permissions.py`      │ Verifier les permissions d'un user test          │
  │                                     │ Usage : `python scripts/check_permissions.py`    │
  │                                     │ `<email> <password>`                             │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Relation pharmacien-pharmacie

La relation est **N:N** :

  ┌────────────────────────────┬────────────────────────────────────────────────────────┐
  │ Cas                        │ Gestion                                                │
  ├────────────────────────────┼────────────────────────────────────────────────────────┤
  │ 1 pharmacien, 1 pharmacie  │ 1 rôle Superset, 1 règle RLS                           │
  ├────────────────────────────┼────────────────────────────────────────────────────────┤
  │ 2 pharmaciens, 1 pharmacie │ Même rôle Superset, même règle RLS                     │
  │ (titulaire + adjoint)      │ Ils voient exactement les mêmes données                │
  ├────────────────────────────┼────────────────────────────────────────────────────────┤
  │ 1 titulaire, N pharmacies  │ 1 rôle avec N règles RLS (OR)                          │
  │                            │ ou N rôles (1 par pharmacie)                           │
  └────────────────────────────┴────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Approches testées et abandonnées

Lors des tests E2E (avril 2026), plusieurs approches ont été testées avant d'arriver à l'architecture retenue :

  ┌────┬────────────────────────────────────┬─────────────────────────────────────────────────┐
  │ #  │ Approche                           │ Raison de l'abandon                             │
  ├────┼────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ 1  │ Multi-connexion Metabase +         │ La copie de dashboard corrompt les field IDs    │
  │    │ Row Access Policy Snowflake +      │ internes de Metabase. Le remap des IDs casse    │
  │    │ copie dashboards + remap field IDs │ les cartes originales.                          │
  ├────┼────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ 2  │ Multi-connexion Metabase +         │ Metabase ne redirige pas les requêtes d'un      │
  │    │ dashboards partagés (sans copie)   │ dashboard vers une autre connexion. Erreur      │
  │    │                                    │ "permission denied" si le user n'a pas accès    │
  │    │                                    │ à la connexion de la carte.                     │
  ├────┼────────────────────────────────────┼─────────────────────────────────────────────────┤
  │ 3  │ Connexion unique Metabase +        │ Fonctionne pour les données mais Metabase OSS   │
  │    │ permissions collections            │ ne permet pas de rendre les dashboards          │
  │    │                                    │ read-only ("Vue" = voir + modifier).            │
  └────┴────────────────────────────────────┴─────────────────────────────────────────────────┘

Les Row Access Policies Snowflake et les secure functions créées lors des tests restent en place (dormantes, non attachées aux tables). Elles pourront être réactivées si migration vers Metabase Pro.

[↑ Retour au sommaire](#table-des-matières)

---

## Limites et points de vigilance

  ┌────┬──────────────────────────────────┬────────────────────────────────────────────────┐
  │ #  │ Limite                           │ Mitigation                                     │
  ├────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ L1 │ Metabase OSS : dashboards        │ Historique Metabase permet la restauration.    │
  │    │ modifiables par les users "Vue"  │ Risque faible en pratique.                     │
  ├────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ L2 │ Deux outils BI en parallèle      │ Même source Snowflake, pas de conflit.         │
  │    │ (Metabase + Superset)            │ Migration progressive possible.                │
  ├────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ L3 │ 16 dashboards à recréer dans     │ Effort unique. API Superset pour automatiser.  │
  │    │ Superset                         │                                                │
  ├────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ L4 │ Filtre Pharmacie sur hash MD5    │ Intentionnel (option A1) : les hash sont       │
  │    │ (pas de noms lisibles)           │ incompréhensibles → sécurité par obscurité     │
  │    │                                  │ sur Metabase. Superset filtre automatiquement. │
  ├────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ L5 │ Provisionnement 1x/jour (nuit)   │ Nouvelle pharmacie visible le lendemain matin  │
  └────┴──────────────────────────────────┴────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Fichiers impactés

  ┌────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
  │ Fichier                                    │ Rôle                                                   │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `scripts/metabase_maintenance.py`          │ Provisionnement a la demande (auto-auth, autonome)     │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `scripts/provision_rls.py`                 │ Ancien script (conserve, remplace par maintenance.py)  │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `scripts/DDL_TABLES.sql`                   │ Tables AUDIT (RLS_PHARMACY_ACCESS + RLS_PROVISION_LOG) │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `scripts/DDL_WH.sql`                       │ Row Access Policies + secure functions (dormantes)     │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `scripts/fix_cards_db.py`                  │ Utilitaire restauration database_id des cartes         │
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `dbt/macros/rls_reapply.sql`               │ Macro on-run-end (dormante, utilisable si Metabase Pro)│
  ├────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ `dbt/dbt_project.yml`                      │ Hook on-run-end désactivé                              │
  └────────────────────────────────────────────┴────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Dépannage

  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Problème                             │ Solution                                                 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Dashboard Admin modifié par un user  │ Ouvrir le dashboard → icône horloge (historique)         │
  │                                      │ → restaurer la version précédente                        │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Cartes affichent "Champ inconnu"     │ Les cartes ont un mauvais database_id. Lancer :          │
  │ ou triangles jaunes                  │ `python scripts/fix_cards_db.py <token>`                 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Nouvelle pharmacie a provisionner     │ 1. Verifier que la pharmacie est dans dim_pharmacie :     │
  │                                      │    `SELECT * FROM MARTS.DIM_PHARMACIE WHERE PHA_ID=XXX`  │
  │                                      │ 2. Si presente, lancer :                                  │
  │                                      │    `python scripts/metabase_maintenance.py`               │
  │                                      │    (auto-auth, detecte et provisionne automatiquement)    │
  │                                      │ 3. Si absente : le CDC ou dbt n'a pas encore traite.      │
  │                                      │    Attendre le prochain cycle batch_loop.                  │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)
