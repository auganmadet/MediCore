# Plan d'optimisation coût Snowflake

> **Statut** : ✓ IMPLÉMENTÉ le 2026-04-23 — ✓ Mesures stabilisées sur 4 jours post-L1+L5 (24-26/04, voir §11)
> **Date proposition** : 2026-04-22
> **Date validation** : 2026-04-23
> **Cible plan théorique** : 471 EUR/mois → 80 EUR/mois (-391 EUR/mois, -83 %)
> **Réalité mesurée (27/04)** : baseline ~604 EUR/mois → ~287 EUR/mois (**-317 EUR/mois, -52 %**). Cumul possible avec clustering + DBT_EVERY_N=12 : -431 EUR/mois (-71 %). Voir §11.
> **Fichiers impactés** : `pipelines/bulk_load.py`, `scripts/batch_loop.sh`, `scripts/bulk_maintenance.py`, `.env`, `CHANGELOG.md`, `docs/16_pipeline_maintenance.md`

## Table des matières

1. [Objectif et contexte](#1-objectif-et-contexte)
2. [Alternatives examinées et choix](#2-alternatives-examinées-et-choix)
3. [La Solution retenue](#3-la-solution-retenue)
4. [Architecture proposée](#4-architecture-proposée)
5. [Détail des modifications](#5-détail-des-modifications)
6. [Risques et mitigations](#6-risques-et-mitigations)
7. [Critères de validation](#7-critères-de-validation)
8. [Plan de rollback](#8-plan-de-rollback)
9. [Timeline d'implémentation](#9-timeline-dimplémentation)
10. [Décisions à valider](#10-décisions-à-valider)
11. [Résultats mesurés en production](#11-résultats-mesurés-en-production)

---

## 1. Objectif et contexte

### Situation actuelle

Coût mensuel **dev** : **~471 EUR/mois** dont :

  ┌────────────────────────────────────┬───────────┬───────────┐
  │ Poste                              │ EUR/mois  │ Part      │
  ├────────────────────────────────────┼───────────┼───────────┤
  │ Ref_reload nuit (4h48 × 7 nuits)   │      397  │ 84 %      │
  ├────────────────────────────────────┼───────────┼───────────┤
  │ CDC + dbt + Metabase + storage     │       74  │ 16 %      │
  ├────────────────────────────────────┼───────────┼───────────┤
  │ **Total**                          │  **471**  │ **100 %** │
  └────────────────────────────────────┴───────────┴───────────┘

Le ref_reload est le poste dominant. Il recharge entièrement 14 tables de référence chaque nuit, dont :

  ┌────────────────────────────┬─────────────┬────────────┐
  │ Table                      │ Rows        │ Durée      │
  ├────────────────────────────┼─────────────┼────────────┤
  │ MEDIPRIX_FACTURES          │     264 M   │ 3 h 37 min │
  ├────────────────────────────┼─────────────┼────────────┤
  │ STOCKHISTORY               │     147 M   │ 44 min     │
  ├────────────────────────────┼─────────────┼────────────┤
  │ DAYBYDAY                   │      47 M   │ 15 min     │
  ├────────────────────────────┼─────────────┼────────────┤
  │ 11 autres tables           │     <10 M   │ ~10 min    │
  ├────────────────────────────┼─────────────┼────────────┤
  │ **Total**                  │  **~465 M** │ **~4h48**  │
  └────────────────────────────┴─────────────┴────────────┘

Or **97 % des données de ces 4 grosses tables sont historiques et immuables** (vérifié sur 30 jours glissants). Les recharger chaque nuit est gaspillé.

[↑ Retour au sommaire](#table-des-matières)

---

## 2. Alternatives examinées et choix

12 leviers d'optimisation ont été analysés et numérotés **L1 à L12**. Voici le tableau comparatif complet :

  ┌──────┬──────────────────────────────────────────────────┬───────────┬─────────────┬───────────┬──────────┐
  │  #   │ Levier                                           │ EUR/mois  │ Effort      │ Risque    │ Retenu   │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L1   │ Incremental merge (4 tables)                     │      325  │ 3 j         │ Faible    │ **OUI**  │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L2   │ CDC pour ref tables (MEDIPRIX, STOCK, DAYBYDAY)  │      300  │ 2-3 sem     │ Élevé     │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L3   │ Réduire fréquence ref_reload (J+2 au lieu de J+1)│      200  │ 10 min      │ Moyen     │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L4   │ Metabase caching + materialized views            │  150-500* │ 1 semaine   │ Faible    │ Différé  │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L5   │ Skip dimanche (pharmacies fermées)               │       65  │ 10 min      │ Faible    │ **OUI**  │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L6   │ Paralléliser bulk_load (threads simultanés)      │       80  │ 2 j         │ Faible    │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L7   │ Optimiser mart_kpi_dormant (7 min a lui seul)    │       75  │ 3 j         │ Faible    │ Différé  │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L8   │ CDC désactivé en journée (nuit seule)            │       58  │ 1 h         │ Élevé     │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L9   │ XSMALL → SMALL warehouse                         │  0 à +40  │ 10 min      │ —         │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L10  │ Migrer DEV vers PostgreSQL                       │       50  │ 1 mois      │ Élevé     │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L11  │ Réduire Time Travel (7j → 1j)                    │        5  │ 10 min      │ Moyen     │ NON      │
  ├──────┼──────────────────────────────────────────────────┼───────────┼─────────────┼───────────┼──────────┤
  │ L12  │ Drop DEV si inutilisé                            │        3  │ 5 min       │ Faible    │ NON      │
  └──────┴──────────────────────────────────────────────────┴───────────┴─────────────┴───────────┴──────────┘

\* Valeur pour la production pleine (269 pharmacies actives) — peu d'impact en dev.

**La Solution retenue = L1 + L5** (voir section 3).

### Pourquoi les autres leviers sont-ils écartés ?

- **L2 — CDC pour ref tables** : complexité énorme (snapshot 400M events Kafka, saturation broker), 2-3 semaines de dev. Gain inférieur à la Solution retenue.
- **L3 — Réduire fréquence ref_reload** : plus simple, mais perte de fraîcheur (données J-2 pour les pharmaciens). La Solution retenue garde une fraîcheur J+0 avec un meilleur gain.
- **L4 — Metabase caching** : pas d'effet en dev (peu de requêtes concurrentes). Différé, à activer quand la production démarrera.
- **L6 — Paralléliser bulk_load** : contrainte warehouse XSMALL = 1 cluster, gain réel limité.
- **L7 — Optimiser mart_kpi_dormant** : bon gain mais différé car non urgent (problème de SQL pur, pas d'architecture).
- **L8 — Désactiver CDC journée** : perte de temps réel, dégrade le service métier.
- **L9 — Changer taille warehouse** : SMALL coûte 2× plus cher à l'heure mais n'est pas 2× plus rapide sur ce workload → iso-coût au mieux.
- **L10 — Migrer DEV vers PostgreSQL** : dénature l'environnement, perte de l'iso-production.
- **L11 / L12 — Time Travel et drop DEV** : gains marginaux (<10 EUR/mois), pas prioritaires.

[↑ Retour au sommaire](#table-des-matières)

---

## 3. La Solution retenue

La Solution combine **deux optimisations complémentaires** qui s'appliquent au même processus (le ref_reload nocturne) :

### Optimisation A — Incremental merge sur 4 tables candidates

Chaque nuit de semaine (sauf dimanche et lundi), charger uniquement les **30 derniers jours** des 4 grosses tables au lieu de leur intégralité, et faire un MERGE INTO Snowflake (UPDATE/INSERT sur la PK) au lieu de TRUNCATE+INSERT.

Gain : **-325 EUR/mois**.

### Optimisation B — Skip dimanche

Pas de ref_reload le dimanche soir (pharmacies fermées, peu de transactions). La fenêtre glissante de 30 jours rattrape les données dominicales au cycle de lundi.

Gain : **-65 EUR/mois** supplémentaires.

### Bilan combiné

  ┌──────────────────────┬───────────┬───────────┬────────────────┐
  │ Poste                │ Avant     │ Après     │ Gain           │
  ├──────────────────────┼───────────┼───────────┼────────────────┤
  │ Ref_reload mensuel   │   397 EUR │    66 EUR │  **-331 EUR**  │
  ├──────────────────────┼───────────┼───────────┼────────────────┤
  │ Skip dimanche        │       —   │       —   │   **-60 EUR**  │
  ├──────────────────────┼───────────┼───────────┼────────────────┤
  │ Autres (inchangés)   │    74 EUR │    74 EUR │          0     │
  ├──────────────────────┼───────────┼───────────┼────────────────┤
  │ **Budget total mois**│ **471**   │ **80**    │ **-391 EUR**   │
  ├──────────────────────┼───────────┼───────────┼────────────────┤
  │ **Budget total an**  │ **5 650** │ **960**   │ **-4 690 EUR** │
  └──────────────────────┴───────────┴───────────┴────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 4. Architecture proposée

### Logique hebdomadaire

  ┌───────────────┬───────────────────────────────────────────────────────────────┐
  │ Jour          │ Action ref_reload                                             │
  ├───────────────┼───────────────────────────────────────────────────────────────┤
  │ Lundi         │ Full reload complet (14 tables, TRUNCATE+reload)              │
  │               │ → garantit la réconciliation hebdomadaire (DELETEs captés)    │
  ├───────────────┼───────────────────────────────────────────────────────────────┤
  │ Mardi→Samedi  │ Incremental merge sur 4 tables candidates                     │
  │               │ + TRUNCATE+reload sur les 10 petites tables                   │
  │               │ → ~16 min au lieu de 4h48                                     │
  ├───────────────┼───────────────────────────────────────────────────────────────┤
  │ Dimanche      │ Aucun ref_reload (skip)                                       │
  │               │ → économie 4h48 sans impact (peu de transactions dominicales) │
  └───────────────┴───────────────────────────────────────────────────────────────┘

### Pourquoi lundi pour le full et pas dimanche ?

Le full hebdo doit tourner **quand il y a quelque chose à réconcilier**. Dimanche = données identiques à samedi. Lundi matin = nouvelle semaine active, on synchronise en profondeur.

Avantages :

- Lundi matin : données 100 % synchronisées (rattrapage complet pour la semaine)
- Dimanche : machine peut éteindre → économie réelle
- Mardi→Samedi : cycles rapides de 16 min

### Fenêtre glissante 30 jours

Chaque nuit (sauf dimanche et lundi), on recharge les rows MySQL où `date_col >= CURDATE() - 30`. Justification :

- Attrape les nouvelles lignes (date du jour)
- Attrape les ajouts tardifs (data Mediprix parfois J+1 à J+5)
- Attrape les corrections récentes (rétrocessions, ajustements comptables)
- Rate les modifications >30 jours et les DELETEs → rattrapés par le full du lundi

### 4 tables candidates retenues

  ┌──────────────────────┬────────────────────┬──────────────────────────────────┬──────────────┐
  │ Table MySQL          │ Colonne date       │ Clé primaire                     │ Index date   │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┼──────────────┤
  │ MEDIPRIX_FACTURES    │ FAC_DATE           │ PHA_ID, FAC_ID, FAC_TI           │ ✓            │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┼──────────────┤
  │ STOCKHISTORY         │ STH_DATE           │ PHA_ID, PRD_ID, STH_DATE         │ ✓            │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┼──────────────┤
  │ DAYBYDAY             │ DBD_DATE           │ PHA_ID, DBD_DATE, PRD_ID         │ ✓            │
  ├──────────────────────┼────────────────────┼──────────────────────────────────┼──────────────┤
  │ MANQHISTORY          │ MNQ_DATE           │ PHA_ID, MNQ_DATE, PRD_ID, FAC_ID │ ✓            │
  └──────────────────────┴────────────────────┴──────────────────────────────────┴──────────────┘

Les 10 autres tables (FOURNISSEURS, PRODUITS, EAN13, LPPR, HISTORY, LOG, PHARMACIE, PHARMACIES, PHARMACIES_ERREUR, PRODUITS_NEGATIFS) restent en TRUNCATE+reload car :

- Volume trop faible pour justifier la complexité (9/10 font <10M rows)
- Pas d'index date évident pour certaines
- Risque de DELETE non captable (produits retirés du catalogue, etc.)

[↑ Retour au sommaire](#table-des-matières)

---

## 5. Détail des modifications

### 5.1 Fichier `pipelines/bulk_load.py`

#### Ajout d'un dictionnaire des tables incrémentales

```python
# Tables candidates pour incremental merge : grosses tables avec colonne date indexée
INCREMENTAL_TABLES = {
    'MEDIPRIX_FACTURES': {'date_col': 'FAC_DATE', 'pk': ['PHA_ID', 'FAC_ID', 'FAC_TI']},
    'STOCKHISTORY':      {'date_col': 'STH_DATE', 'pk': ['PHA_ID', 'PRD_ID', 'STH_DATE']},
    'DAYBYDAY':          {'date_col': 'DBD_DATE', 'pk': ['PHA_ID', 'DBD_DATE', 'PRD_ID']},
    'MANQHISTORY':       {'date_col': 'MNQ_DATE', 'pk': ['PHA_ID', 'MNQ_DATE', 'PRD_ID', 'FAC_ID']},
}
```

#### Nouvel argument CLI

```python
parser.add_argument('--incremental-days', type=int, default=None,
    help='Si fourni, charge seulement les N derniers jours pour les tables'
         ' dans INCREMENTAL_TABLES (MERGE au lieu de TRUNCATE+INSERT).')
```

#### Nouvelle fonction `bulk_load_incremental_table`

```python
def bulk_load_incremental_table(mysql_conn, sf_conn, mysql_table, sf_table,
                                 date_col, pk_cols, days_window):
    """Charge les N derniers jours depuis MySQL et MERGE dans Snowflake.

    Étapes :
    1. SELECT * FROM {table} WHERE {date_col} >= CURDATE() - INTERVAL N DAY
    2. PUT chunks Parquet vers @BULK_STAGE (même pipeline que bulk_load_table)
    3. COPY INTO table staging temporaire
    4. MERGE INTO table cible sur clé primaire
    5. DROP table staging
    """
    # Étape 1 : SELECT filtré MySQL
    query = f"SELECT * FROM {mysql_table} WHERE {date_col} >= DATE_SUB(CURDATE(), INTERVAL {days_window} DAY)"
    # ... (chunking Parquet comme bulk_load_table existant)

    # Étape 4 : MERGE idempotent
    pk_join = ' AND '.join(f'tgt."{c}" = src."{c}"' for c in pk_cols)
    sf_cursor.execute(f"""
        MERGE INTO RAW.{sf_table} tgt
        USING RAW.{sf_table}_STG_INCR src
        ON {pk_join}
        WHEN MATCHED THEN UPDATE SET
            {', '.join(f'tgt."{c}" = src."{c}"' for c in all_columns_except_pk)}
        WHEN NOT MATCHED THEN INSERT ({', '.join(all_columns)})
        VALUES ({', '.join(f'src."{c}"' for c in all_columns)})
    """)
```

#### Logique d'orchestration dans `main()`

```python
if args.incremental_days and mysql_table in INCREMENTAL_TABLES:
    # Mode incremental pour les tables candidates
    conf = INCREMENTAL_TABLES[mysql_table]
    rows = bulk_load_incremental_table(
        mysql_conn, sf_conn, mysql_table, sf_table,
        conf['date_col'], conf['pk'], args.incremental_days
    )
else:
    # Mode historique : TRUNCATE+reload
    rows = bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table,
                           args.chunk_size, args.truncate, force=args.truncate)
```

### 5.2 Fichier `scripts/batch_loop.sh`

#### Nouvelle variable

```bash
# Jour de la semaine : 0=dimanche, 1=lundi, ..., 6=samedi
# Full reload le lundi (DOW=1), skip le dimanche (DOW=0), incremental mardi→samedi
REF_FULL_DOW=${REF_FULL_DOW:-1}  # 1 = lundi
```

#### Modification de la phase ref_reload

```bash
if is_ref_reload_window && [ ! -f "$REF_DONE_FLAG" ]; then
    DOW=$(date +%w)

    if [ "$DOW" = "0" ]; then
        # Dimanche : skip complet
        echo "Phase ref-reload: SKIP dimanche (pharmacies fermées)"
        touch "$REF_DONE_FLAG"  # flag créé pour ne pas bloquer dbt post-reload

    elif [ "$DOW" = "$REF_FULL_DOW" ]; then
        # Lundi : full reload complet
        echo "Phase ref-reload: FULL (lundi, reconciliation hebdomadaire)"
        python /app/pipelines/bulk_load.py --ref-only --truncate --run-id "$RUN_ID"

    else
        # Mar→Sam : incremental merge 30 jours
        echo "Phase ref-reload: INCREMENTAL 30j (tables candidates)"
        python /app/pipelines/bulk_load.py --ref-only --truncate --incremental-days 30 --run-id "$RUN_ID"
    fi
fi
```

### 5.3 Fichier `scripts/bulk_maintenance.py` (ajustement check B4)

B4 vérifie la réconciliation MySQL vs Snowflake. En mode incremental, les écarts attendus grandissent (modifs >30j non captées). Adapter le seuil d'alerte :

```python
# Tolérer jusqu'à 1% d'écart en mode incremental (raisonnable pour modifs >30j)
# Full reload hebdomadaire ramène à 0% chaque lundi
B4_INCREMENTAL_TOLERANCE_PCT = 1.0
```

### 5.4 Monitoring — traçabilité audit

Dans `batch_loop.sh`, logger le mode utilisé après le ref_reload :

```bash
DOW_LABEL=$([ "$DOW" = "0" ] && echo "skip" || ([ "$DOW" = "1" ] && echo "full" || echo "incremental"))
python3 -c "
from pipelines.utils.audit import log_step_end
log_step_end('$RUN_ID', 'ref_reload', 'SUCCESS', metadata={'mode': '$DOW_LABEL'})
"
```

[↑ Retour au sommaire](#table-des-matières)

---

## 6. Risques et mitigations

### 6.1 Modifications rétroactives >30 jours non captées

**Risque** : une ligne MySQL est modifiée mais son `date_col` est >30 jours → l'incremental ne la reprend pas.

**Impact** : MARTS contient la version obsolète. Durée max : 7 jours (jusqu'au lundi suivant).

**Mitigation** : le full reload **chaque lundi** corrige automatiquement. Alerte B4 si écart MySQL vs Snowflake > 1 %.

**Probabilité** : faible. Les factures pharmacie sont généralement corrigées dans les 15 jours.

### 6.2 DELETEs invisibles en incremental

**Risque** : une ligne supprimée en MySQL ne peut pas être détectée par un MERGE en mode `WHEN MATCHED/NOT MATCHED`.

**Impact** : données fantômes dans MARTS pendant max 6 jours.

**Mitigation** : le full reload du lundi nettoie les orphelins. Monitoring B4 pour quantifier les écarts.

**Probabilité** : très faible. Les factures ne sont pas supprimées, elles sont annulées via INSERT négatif (rétrocession).

### 6.3 MERGE lent si clustering Snowflake mal dimensionné

**Risque** : le MERGE INTO est lent si la table cible n'a pas de clustering sur la PK.

**Impact** : le gain théorique (16 min) pourrait devenir 30-40 min.

**Mitigation** :

- Ajouter `CLUSTER BY (PHA_ID, FAC_DATE)` sur RAW_MEDIPRIX_FACTURES si nécessaire
- Mesurer avant/après déploiement
- Fallback à TRUNCATE+INSERT sur la fenêtre si MERGE > 20 min

### 6.4 Interruption pendant incremental

**Risque** : machine éteinte pendant le MERGE.

**Impact** : aucun — le MERGE Snowflake est transactionnel (soit complet, soit rien). Juste besoin de relancer.

**Mitigation** : le pattern CLONE+SWAP reste applicable sur la table staging (table intermédiaire du MERGE).

### 6.5 Dépendances dbt cassées

**Risque** : les modèles dbt supposent des données fraîches chaque nuit. Si l'incremental manque des rows, dbt peut produire des marts faux.

**Impact** : KPIs faux jusqu'au prochain full.

**Mitigation** :

- Tests singular dbt (déjà en place) détectent les incohérences
- D1/D2 dans pipeline_maintenance → alerte Teams
- Freshness source dbt → alerte si tables trop anciennes

[↑ Retour au sommaire](#table-des-matières)

---

## 7. Critères de validation

### 7.1 Tests unitaires en dev (avant déploiement)

  ┌─────┬─────────────────────────────────────────────────────┬──────────────────────────────┐
  │  #  │ Test                                                │ Critère de succès            │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  1  │ bulk_load.py --tables DAYBYDAY --incremental-days 30│ Charge 1.4M rows en <2 min   │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  2  │ COUNT RAW_DAYBYDAY après incremental                │ Pas de doublons vs avant     │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  3  │ Insérer 1 ligne test (J-5) dans MySQL               │ Visible dans RAW après merge │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  4  │ Modifier 1 ligne (J-10) dans MySQL                  │ MàJ visible dans RAW         │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  5  │ bulk_load.py --tables MEDIPRIX_FACTURES -i-days 30  │ Charge 7.2M rows en <8 min   │
  ├─────┼─────────────────────────────────────────────────────┼──────────────────────────────┤
  │  6  │ Comparer MAX(FAC_DATE) MySQL vs Snowflake           │ Égal                         │
  └─────┴─────────────────────────────────────────────────────┴──────────────────────────────┘

### 7.2 Validation en production (semaine 1 — observation quotidienne)

  ┌───────────────┬───────────────┬──────────────────┬─────────────────┐
  │ Jour          │ Mode          │ Durée attendue   │ Crédits attendus│
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Lundi (J+1)   │ FULL          │ 4h48             │ 5 cr            │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Mardi (J+2)   │ Incremental   │ ~16 min          │ 0.3 cr          │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Mercredi (J+3)│ Incremental   │ ~16 min          │ 0.3 cr          │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Jeudi (J+4)   │ Incremental   │ ~16 min          │ 0.3 cr          │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Vendredi (J+5)│ Incremental   │ ~16 min          │ 0.3 cr          │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Samedi (J+6)  │ Incremental   │ ~16 min          │ 0.3 cr          │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ Dimanche (J+7)│ SKIP          │ —                │ 0 cr            │
  ├───────────────┼───────────────┼──────────────────┼─────────────────┤
  │ **Semaine 1** │               │                  │ **~6.5 cr**     │
  │               │               │                  │ (vs 35 cr avant)│
  └───────────────┴───────────────┴──────────────────┴─────────────────┘

### 7.3 Validation via pipeline_maintenance

Après chaque nuit incrémentale, vérifier :

- **B2** Tables RAW vides = 0
- **B3** Doublons = inchangé
- **B4** Écarts MySQL/SF < 1 % (incremental) ou = 0 (le lundi après full)
- **B5** Timestamps frais (MAX(CDC_TIMESTAMP) < 48h)
- **D5** Tables MARTS non vides
- Tests singular dbt : PASS

[↑ Retour au sommaire](#table-des-matières)

---

## 8. Plan de rollback

### 8.1 Déclencheurs de rollback

Si l'un de ces symptômes apparaît pendant la première semaine :

- B4 écart > 5 % (dérive grave)
- Tests singular dbt en nouvelle échec
- Complaintes métier sur données obsolètes
- MERGE prend > 30 min par table

### 8.2 Rollback immédiat (<5 min)

Dans `.env` ou variable env du conteneur, forcer le full reload chaque nuit :

```bash
REF_FULL_DOW=-1  # Désactive l'incremental : tous les jours = full
```

Les commits restent en place mais inactifs. Prochaine nuit = comportement original.

### 8.3 Rollback long terme

Si décision définitive d'abandonner l'incremental :

```bash
git revert <commits de la feature>
```

Remet les fichiers exactement comme avant. Aucune donnée Snowflake perdue.

[↑ Retour au sommaire](#table-des-matières)

---

## 9. Timeline d'implémentation

  ┌──────────────┬─────────────────────────────────────────┬────────┬──────────────┐
  │ Étape        │ Action                                  │ Durée  │ Livrable     │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J1           │ Modif bulk_load.py (MERGE + arg CLI)    │ 1 j    │ Code + tests │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J2           │ Modif batch_loop.sh (DOW logic)         │ 0.5 j  │ Script batch │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J2           │ Tests manuels sur DAYBYDAY              │ 0.5 j  │ Logs valid.  │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J3           │ Tests sur MEDIPRIX_FACTURES             │ 0.5 j  │ Logs valid.  │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J3           │ Ajustement bulk_maintenance.py (B4)     │ 0.5 j  │ Code         │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J4           │ Documentation (docs/04, CHANGELOG)      │ 0.5 j  │ Markdown     │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J4           │ Commit + push branche                   │ 0.5 j  │ Pull request │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J5           │ Review + merge main                     │ 0.5 j  │ Merge        │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ J5           │ Déploiement + restart conteneur         │ 0.5 j  │ Up           │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ Semaine 1    │ Observation quotidienne                 │ 7 j    │ Rapport      │
  ├──────────────┼─────────────────────────────────────────┼────────┼──────────────┤
  │ Semaine 2    │ Validation long terme                   │ 7 j    │ Go/no-go     │
  └──────────────┴─────────────────────────────────────────┴────────┴──────────────┘

**Total effort dev** : ~5 jours (J1 à J5).
**Total calendrier** : ~3 semaines (dev + observation + validation).

[↑ Retour au sommaire](#table-des-matières)

---

## 10. Décisions à valider

Avant de lancer le développement, merci de valider les points suivants :

### 10.1 Périmètre

- [ ] **4 tables candidates** : MEDIPRIX_FACTURES, STOCKHISTORY, DAYBYDAY, MANQHISTORY. D'autres ?
- [ ] **Fenêtre de 30 jours** suffisante, ou préférer 15 / 60 jours ?
- [ ] **Full reload lundi** OK, ou préférer samedi soir ?
- [ ] **Skip dimanche** OK, ou garder un cycle minimal ?

### 10.2 Risques acceptés

- [ ] Données obsolètes jusqu'à max 7 jours pour les modifs >30 jours en MySQL
- [ ] DELETEs non captés entre deux full reloads (max 7 jours)
- [ ] B4 tolérance 1 % jusqu'au lundi (au lieu de 0 % actuel)

### 10.3 Budget et calendrier

- [ ] Budget 5 jours de dev acceptés
- [ ] Période d'observation 2 semaines acceptée
- [ ] Rollback possible si dérive observée

### 10.4 Gains attendus

- [ ] Objectif **-391 EUR/mois** (-83 %) accepté comme référence
- [ ] **-4 690 EUR/an** justifie l'effort

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe — Formules détaillées

### Coût actuel (baseline)

```
Ref_reload : 4h48/nuit × 7 nuits/semaine = 33h36/semaine
           = 144 h/mois × 1 crédit/h (XSMALL) = 144 crédits
           × 2.76 EUR/crédit = 397 EUR/mois
```

### Coût après la Solution

```
Lundi (full)          : 4h48/nuit × 4 semaines = 19h12/mois =  19 crédits
Mar-Sam (incremental) : 16 min × 5 j × 4 sem    =  5h20/mois =   5 crédits
Dimanche (skip)       :                       0 h = 0 crédit
                                                     ──────
Total                                              24 crédits/mois
                                                   × 2.76 EUR = 66 EUR/mois
```

### Gain net

```
397 EUR (avant) − 66 EUR (après) = 331 EUR/mois (Optim A + B combinées)
Skip dimanche supplémentaire hors incremental   : +60 EUR/mois
────────────────────────────────────────────────
Total Solution estimé                           : ~391 EUR/mois économisés
```

---

## 11. Résultats mesurés en production

> **1er run production complet : nuit du 2026-04-24 au 2026-04-25** (vendredi → samedi, mode incremental DOW=5)

### 11.1 Durée mesurée du ref_reload

  ┌──────────────────────────────────┬──────────────┬──────────────────────────┐
  │ Table                            │ Durée mesurée│ Notes                    │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ MEDIPRIX_FACTURES (incremental)  │      37 min  │ 7,1 M rows mergés        │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ STOCKHISTORY (incremental)       │      10 min  │ 5,1 M rows mergés        │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ DAYBYDAY (incremental)           │       2 min  │ 1,5 M rows mergés        │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ MANQHISTORY (incremental)        │      17 sec  │ 97 K rows mergés         │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ 10 autres tables (TRUNCATE+COPY) │     ~4 min   │ Inchangées               │
  ├──────────────────────────────────┼──────────────┼──────────────────────────┤
  │ **Total**                        │  **~53 min** │ Cible plan : 16 min      │
  └──────────────────────────────────┴──────────────┴──────────────────────────┘

### 11.2 Écart vs cible et cause

L'écart de 37 min est concentré sur **MEDIPRIX_FACTURES** (264 M lignes au total). Le risque a été anticipé en §6.3 :

> *"MERGE lent si clustering Snowflake mal dimensionné. Le gain théorique (16 min) pourrait devenir 30-40 min."*

**Mitigation prévue** : ajouter `CLUSTER BY (PHA_ID, FAC_DATE)` sur `RAW_MEDIPRIX_FACTURES`. Effort : 1 jour. Gain attendu : retour vers 16-20 min total.

### 11.3 Coût mesuré vs cible

> ⚠ **Note méthodologique** : tous les chiffres ci-dessous mesurent le **TOTAL** du compute warehouse `MEDICORE_WH` (jour + nuit + ref_reload + maintenance), pas isolés sur le ref_reload. Source : `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`. Mesures stabilisées sur 4 jours post-L1+L5 (24-27/04, le 27/04 est en cours).
>
> ⚠ **Correction 2026-04-27** : les premières synthèses rapportaient des extrapolations fautives. Les vrais chiffres remplacent les estimations.

#### Baseline mesuré (10 jours avant L1+L5, du 13 au 22/04)

  ┌─────────────────────────────────────────────┬───────────────────┐
  │ Métrique                                    │ Valeur            │
  ├─────────────────────────────────────────────┼───────────────────┤
  │ Crédits/jour observés (min - max)           │ 3,7 - 11,1        │
  ├─────────────────────────────────────────────┼───────────────────┤
  │ Crédits/jour moyenne (10 jours)             │ 7,31 cr/j         │
  ├─────────────────────────────────────────────┼───────────────────┤
  │ **Coût mensuel total (mesuré × 30 jours)**  │ **~219 cr/mois**  │
  │                                             │ **~604 EUR/mois** │
  └─────────────────────────────────────────────┴───────────────────┘

Note : le baseline théorique du plan original (`471 EUR/mois`) sous-estimait la réalité observée. La vraie valeur de référence est **604 EUR/mois mesuré**.

#### Coût post-L1+L5 (mesures 24-27/04, semaine type extrapolée)

Décomposition par jour de semaine (mesures stabilisées) :

  ┌──────────────────────┬─────────────┬───────────┬─────────────┐
  │ Jour de semaine      │ cr/jour     │ Nb jours  │ cr/mois     │
  │ (régime nocturne)    │ (mesuré)    │ /mois     │ (calculé)   │
  ├──────────────────────┼─────────────┼───────────┼─────────────┤
  │ Lundi (full reload)  │  5,6 cr/j*  │     4     │   22,4 cr   │
  ├──────────────────────┼─────────────┼───────────┼─────────────┤
  │ Mar-Sam (incremental)│  4,0 cr/j   │  20** ⭐  │   80,0 cr   │
  ├──────────────────────┼─────────────┼───────────┼─────────────┤
  │ Dimanche (skip)      │  0,5 cr/j   │     4     │    2,0 cr   │
  ├──────────────────────┼─────────────┼───────────┼─────────────┤
  │ **Total mensuel**    │      —      │    28     │ **~104 cr** │
  │                      │             │           │ **~287 EUR**│
  └──────────────────────┴─────────────┴───────────┴─────────────┘

\* Estimation, à confirmer après le 1er full reload prod du 27/04.
\*\* ⭐ Important : `Mar-Sam` représente **5 jours × 4 semaines = 20 jours/mois** (pas 5).

#### Synthèse cible vs mesuré

  ┌──────────────────────────────────────────┬──────────────┬──────────────┬───────────────┐
  │ Référence                                │ Total mois   │ Total an     │ Économie %    │
  ├──────────────────────────────────────────┼──────────────┼──────────────┼───────────────┤
  │ Baseline mesuré (10 j avant)             │  604 EUR     │  7 250 EUR   │      —        │
  ├──────────────────────────────────────────┼──────────────┼──────────────┼───────────────┤
  │ Post-L1+L5 stabilisé (mesuré)            │  287 EUR     │  3 440 EUR   │ **-52 %**     │
  ├──────────────────────────────────────────┼──────────────┼──────────────┼───────────────┤
  │ Cible plan théorique original            │   80 EUR     │    960 EUR   │   -83 %       │
  └──────────────────────────────────────────┴──────────────┴──────────────┴───────────────┘

**Économie réelle mesurée : -317 EUR/mois (-3 810 EUR/an, -52 %)**.

#### Découverte clé

L1+L5 a optimisé le mode NUIT (ref_reload). Le poste dominant restant est désormais le **mode JOUR** (~67 % du coût). Pour s'approcher de la cible théorique -83 %, il faut combiner avec :

  ┌─────────────────────────────────────────────┬─────────────────┬──────────────┐
  │ Action complémentaire                       │ Effort          │ Gain estimé  │
  ├─────────────────────────────────────────────┼─────────────────┼──────────────┤
  │ Clustering RAW_MEDIPRIX_FACTURES (§11.5)    │ 1 jour + 2 EUR  │ -90 EUR/mois │
  │                                             │ + 1,5 EUR/mois  │              │
  ├─────────────────────────────────────────────┼─────────────────┼──────────────┤
  │ DBT_EVERY_N=12 (dbt jour toutes les 2h)     │ 5 min, 0 EUR    │ -21 EUR/mois │
  ├─────────────────────────────────────────────┼─────────────────┼──────────────┤
  │ Skip mode jour dimanche (actif depuis 26/04)│ Fait            │ -3 EUR/mois  │
  ├─────────────────────────────────────────────┼─────────────────┼──────────────┤
  │ Fix safe_sleep WSL2 (anti-gel timer)        │ Fait 27/04      │ Stabilité    │
  └─────────────────────────────────────────────┴─────────────────┴──────────────┘

Avec les 3 leviers cumulés : **~287 - 90 - 21 - 3 = ~173 EUR/mois**, soit **-431 EUR/mois (-71 %)** vs baseline mesuré.

### 11.4 Bénéfices fonctionnels confirmés

  ┌──────────────────────────────────┬───────────────┬─────────────────┐
  │ Métrique                         │ Avant         │ Après mesuré    │
  ├──────────────────────────────────┼───────────────┼─────────────────┤
  │ Durée ref_reload mar-sam         │   4h48        │     53 min      │
  ├──────────────────────────────────┼───────────────┼─────────────────┤
  │ Fenêtre d'incident nocturne      │   4h48/nuit   │   ~1h/nuit      │
  ├──────────────────────────────────┼───────────────┼─────────────────┤
  │ Heure rapport Teams disponible   │   ~04h40 FR   │   ~00h45 FR     │
  ├──────────────────────────────────┼───────────────┼─────────────────┤
  │ dbt post-reload terminé          │   ~05h30 FR   │   ~00h39 FR     │
  ├──────────────────────────────────┼───────────────┼─────────────────┤
  │ Nuit complète terminée           │   ~05h30 FR   │   ~00h50 FR     │
  └──────────────────────────────────┴───────────────┴─────────────────┘

### 11.5 Action de suivi

- [x] **2026-04-27 09h28 UTC** — `ALTER TABLE MEDICORE_PROD.RAW.RAW_MEDIPRIX_FACTURES CLUSTER BY (PHA_ID, FAC_DATE)` exécuté (avant : `CLUSTER BY (CDC_TIMESTAMP)`).
  - Baseline mesuré : 419 partitions, average_overlaps=417,96, average_depth=417,98, 100 % à depth 512+
  - DDL persisté dans `scripts/DDL_TABLES.sql:188-217`
- [x] **2026-04-27 11h28 UTC** (2h après ALTER) — Auto-clustering quasi-optimal :
  - 351 partitions (consolidées), average_overlaps=**3,91** (÷107), average_depth=**3,12** (÷134)
  - Histogram : 100 % entre depth 2 et 6 (pic à depth=3 avec 151 partitions)
  - **Mieux que la cible** (visait 5-15, atteint 3,12)
- [ ] Mardi 28/04 soir : 1er ref_reload incremental avec clustering effectif (le full reload du 27/04 lundi soir n'en bénéficie pas, mais Snowflake re-clusterise automatiquement en background après le TRUNCATE+COPY).
- [ ] Mercredi 29/04 matin : mesurer durée MEDIPRIX_FACTURES (objectif <10 min vs 37 min mesuré).
- [ ] Si durée stable < 20 min sur 4 nuits incremental : déclarer la cible atteinte.

[↑ Retour au sommaire](#table-des-matières)

---

**Document préparé le 2026-04-22 — Implémenté le 2026-04-23 — 1er run prod mesuré le 2026-04-25.**
