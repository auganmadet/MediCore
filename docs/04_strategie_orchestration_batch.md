# Stratégie d'orchestration batch — MediCore

## Table des matières

1. [Contexte](#1-contexte)
2. [Analyse du besoin réel](#2-analyse-du-besoin-réel)
   - [Qui consomme les données ?](#qui-consomme-les-données-)
   - [Quel niveau de fraîcheur est nécessaire ?](#quel-niveau-de-fraîcheur-est-nécessaire-)
   - [Constat : le système précédent](#constat--le-système-précédent-ne-correspondait-pas-au-besoin)
   - [Durées mesurées par phase (PROD)](#durées-mesurées-par-phase-prod)
   - [Problèmes identifiés](#problèmes-identifiés)
   - [Diagnostic](#diagnostic--un-seul-rythme-pour-trois-besoins-différents)
   - [Perspective : orchestrateur](#perspective--migration-vers-un-orchestrateur)
3. [Stratégie mise en place](#3-stratégie-mise-en-place)
   - [Principe : 3 rythmes](#principe--3-rythmes-différents-pour-3-besoins-différents)
   - [Mode jour (07h - 21h)](#mode-jour-07h---21h--cdc-rapide--dbt-périodique)
   - [Coût du redémarrage WH](#coût-du-redémarrage-wh-auto_resume-sur-les-35-cdc-hors-dbt)
   - [Mode nuit (21h - 07h)](#mode-nuit-21h---07h--cycles-réduits)
4. [Récapitulatif 24h](#4-récapitulatif-24h)
5. [Comparaison des coûts](#5-comparaison-des-coûts)
   - [Avant vs Après](#avant-vs-après)
   - [Détail de l'économie](#détail-de-léconomie)
6. [Pourquoi cette stratégie est adéquate](#6-pourquoi-cette-stratégie-est-adéquate-pour-medicore)
   - [Alignement avec le métier pharmacie](#alignement-avec-le-métier-pharmacie)
   - [Fraîcheur adaptée aux usages](#fraîcheur-adaptée-aux-usages)
   - [Données prêtes avant l'ouverture](#données-prêtes-avant-louverture)
   - [Économie sans compromis fonctionnel](#économie-sans-compromis-fonctionnel)
   - [Évolutivité vers un orchestrateur](#évolutivité-vers-un-orchestrateur)
7. [Variables de configuration](#7-variables-de-configuration)
8. [Temps mesurés (ref_reload)](#8-temps-mesurés-ref_reload-25-mars-2026)

---

## 1. Contexte

MediCore est un pipeline ELT industrialisé qui alimente les dashboards Metabase
d'un groupement de pharmacies. Le flux est :

```
MySQL RDS → Kafka CDC → Snowflake RAW → dbt STAGING → dbt MARTS → Metabase
```

Le pipeline traite **~934 millions de lignes** réparties sur 18 tables :

  ┌──────────────────────────────────┬──────────────────┬────────────────────┐
  │ Type                             │ Tables           │ Volume             │
  ├──────────────────────────────────┼──────────────────┼────────────────────┤
  │ CDC (temps réel via Kafka)       │ 4 tables         │ ~471M lignes       │
  ├──────────────────────────────────┼──────────────────┼────────────────────┤
  │ Référence (bulk load quotidien)  │ 14 tables        │ ~463M lignes       │
  ├──────────────────────────────────┼──────────────────┼────────────────────┤
  │ **Total**                        │ **18 tables**    │ **~934M lignes**   │
  └──────────────────────────────────┴──────────────────┴────────────────────┘

L'orchestration est assurée par `batch_loop.sh`, un script bash
qui boucle en continu dans un conteneur Docker.

[↑ Retour au sommaire](#table-des-matières)

---

## 2. Analyse du besoin réel

### Qui consomme les données ?

Les pharmaciens et le siège (GIE) consultent les dashboards Metabase pendant
les heures ouvrables. Les KPIs affichés (marge, stock, ventes, ruptures) sont
à **granularité journalière**. Personne ne consulte les dashboards la nuit.

### Quel niveau de fraîcheur est nécessaire ?

  ┌──────────────────────────────────┬────────────────────────────────────────┐
  │ Donnée                           │ Besoin réel                            │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ CDC (commandes, factures)        │ ~10 min de latence max en journée      │
  │                                  │ (activité pharmacie en temps réel)     │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ dbt staging + marts (KPIs)       │ ~1h de fraîcheur suffit                │
  │                                  │ (KPIs journaliers, pas temps réel)     │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ Référence (produits, pharmacies) │ 1x/jour suffit                         │
  │                                  │ (données quasi-statiques)              │
  ├──────────────────────────────────┼────────────────────────────────────────┤
  │ Nuit (21h-07h)                   │ Aucun besoin temps réel                │
  │                                  │ (aucun utilisateur connecté)           │
  └──────────────────────────────────┴────────────────────────────────────────┘

### Constat : le système précédent ne correspondait pas au besoin

L'ancienne boucle exécutait **toutes les phases** (CDC + dbt staging + dbt
snapshot + dbt marts + tests + freshness) dans un **cycle monolithique de 30
minutes**, 24h/24, 7j/7.

Le point clé : l'intervalle de 30 min est un **sleep après le traitement**,
pas un cycle fixe. Le vrai temps de cycle est :

```
Temps de cycle réel = Durée du batch + Sleep
```

#### Durées mesurées par phase (PROD)

  ┌───────────────────────────────────────┬──────────────────────┐
  │ Phase                                 │ Durée estimée (PROD) │
  ├───────────────────────────────────────┼──────────────────────┤
  │ CDC batch (micro-batch 500 events)    │ 30s - 2 min          │
  ├───────────────────────────────────────┼──────────────────────┤
  │ dbt staging (18 modèles, incrémental) │ 3 - 10 min           │
  ├───────────────────────────────────────┼──────────────────────┤
  │ dbt snapshot (3 modèles)              │ 1 - 3 min            │
  ├───────────────────────────────────────┼──────────────────────┤
  │ dbt marts (26 modèles, incrémental)   │ 5 - 15 min           │
  ├───────────────────────────────────────┼──────────────────────┤
  │ dbt test                              │ 2 - 5 min            │
  ├───────────────────────────────────────┼──────────────────────┤
  │ source freshness                      │ 30s                  │
  ├───────────────────────────────────────┼──────────────────────┤
  │ **Total traitement**                  │ **~12 - 35 min**     │
  ├───────────────────────────────────────┼──────────────────────┤
  │ + Sleep                               │ + 30 min             │
  ├───────────────────────────────────────┼──────────────────────┤
  │ **Cycle réel**                        │ **~42 - 65 min**     │
  └───────────────────────────────────────┴──────────────────────┘

#### Problèmes identifiés

1. **CDC et dbt couplés** : le CDC attendait la fin de dbt (30-40 min) avant
   de pouvoir re-consommer Kafka. Latence réelle CDC : 45-65 min au lieu de 10.
   C'est comme si un restaurant ne servait les clients que toutes les 30 minutes,
   en batch, alors que la cuisine pourrait envoyer les plats au fil de l'eau.

2. **Nuit identique au jour** : 14 cycles dbt inutiles entre 21h et 07h.
   Le warehouse Snowflake tournait en permanence pour aucun utilisateur.

3. **Aucun skip** : même sans nouvelle donnée CDC, dbt tournait à vide.
   Les modèles incrémentaux ne trouvaient rien de nouveau mais consommaient
   ~35 min de compute Snowflake à chaque cycle.

4. **Ref_reload à 03h** : avec ~3h-3h30 de bulk load, les données n'étaient
   pas prêtes à l'ouverture (07h-08h).

5. **Sleep dev illusoire** : en dev (5 min sleep), le cycle réel était de
   17-40 min. Le sleep de 5 min ne représentait que 12-30% du cycle total.

#### Diagnostic : un seul rythme pour trois besoins différents

  ┌───────────────────────────┬───────────────────┬──────────────────────┐
  │ Donnée                    │ Besoin            │ Fréquence idéale     │
  ├───────────────────────────┼───────────────────┼──────────────────────┤
  │ CDC (commandes, factures) │ Quasi temps réel  │ Toutes les 5-10 min  │
  ├───────────────────────────┼───────────────────┼──────────────────────┤
  │ Staging/Marts (dbt)       │ Dashboards à jour │ Toutes les 30-60 min │
  ├───────────────────────────┼───────────────────┼──────────────────────┤
  │ Référence (bulk load)     │ Quotidien         │ 1x/jour              │
  └───────────────────────────┴───────────────────┴──────────────────────┘

La boucle monolithique imposait le même rythme (42-65 min) aux trois,
alors que chacun a un besoin de fraîcheur radicalement différent.
La solution : **découpler les trois composants** avec des fréquences adaptées.

#### Perspective : migration vers un orchestrateur

La séparation CDC / dbt / ref_reload prépare la migration future vers un
orchestrateur (Airflow, Dagster) où chaque composant deviendra une tâche
dans un DAG avec sa propre fréquence et ses retries :
`cdc_consume >> dbt_staging >> dbt_marts`. En attendant, `batch_loop.sh`
implémente cette séparation dans une boucle unique avec des compteurs.

[↑ Retour au sommaire](#table-des-matières)

---

## 3. Stratégie mise en place

### Principe : 3 rythmes différents pour 3 besoins différents

  ┌───────────────────┬─────────────────┬──────────────────────────────────────┐
  │ Composant         │ Rythme          │ Justification                        │
  ├───────────────────┼─────────────────┼──────────────────────────────────────┤
  │ CDC (Kafka → RAW) │ Toutes les 10   │ Latence acceptable pour le suivi     │
  │                   │ min en journée  │ d'activité pharmacie                 │
  ├───────────────────┼─────────────────┼──────────────────────────────────────┤
  │ dbt (RAW → MARTS) │ Toutes les ~60  │ KPIs journaliers : 1h de fraîcheur   │
  │                   │ min en journée  │ invisible pour l'utilisateur         │
  ├───────────────────┼─────────────────┼──────────────────────────────────────┤
  │ Ref_reload (MySQL │ 1x/jour à 23h FR │ CLONE+SWAP, finir avant 04h FR       │
  │ → RAW, 14 tables) │ (21h UTC)       │ pour dbt post-reload à 04h FR        │
  └───────────────────┴─────────────────┴──────────────────────────────────────┘

### Mode jour (07h - 21h) : CDC rapide + dbt périodique

```
Itération :  CDC --- CDC --- CDC --- CDC --- CDC --- CDC+dbt ----
Temps     :  10min   10min   10min   10min   10min   ~40min
              │                                        │
              └── CDC seul (~2 min actif)               └── CDC + dbt complet
                  WH se suspend entre chaque               WH actif ~40 min
```

- **84 cycles CDC** : 1 toutes les 10 min, durée ~2 min chacun (14h × 6 CDC/h)
- **14 cycles dbt** : 1 toutes les 6 itérations CDC (~60 min), durée ~35 min chacun
- **49 CDC tombent pendant un dbt** (WH déjà actif → aucun surcoût)
  - Calcul : chaque dbt dure ~35 min, soit ~3.5 CDC par dbt (35 min ÷ 10 min)
  - 14 dbt × 3.5 CDC/dbt = ~49 CDC absorbés sans redémarrage
- **35 CDC hors dbt** (84 - 49) : seuls cycles qui redémarrent le WH
- **Skip dbt si 0 event CDC** : évite ~35 min de compute inutile

#### Coût du redémarrage WH (AUTO_RESUME) sur les 35 CDC hors dbt

Snowflake facture un minimum de 60 secondes à chaque redémarrage. La question
est : ces redémarrages coûtent-ils plus que de laisser le WH allumé ?

  ┌──────────────────────────────────────┬────────────────────────────────┬────────┐
  │ Scénario                             │ Calcul                         │ Coût   │
  ├──────────────────────────────────────┼────────────────────────────────┼────────┤
  │ WH **se suspend** entre chaque CDC   │ 35 redémarrages × 3 min = 105  │ 1.75h  │
  │                                      │ min facturées                  │        │
  ├──────────────────────────────────────┼────────────────────────────────┼────────┤
  │ WH **reste allumé** entre les CDC    │ 14h continues (même pendant    │ 14h    │
  │                                      │ les pauses entre CDC)          │        │
  └──────────────────────────────────────┴────────────────────────────────┴────────┘

Laisser le WH se suspendre coûte **1.75h** au lieu de **14h** : c'est **8× moins cher**.

Chronologie d'un cycle CDC isolé (hors dbt) :

```
00:00  WH se réveille (AUTO_RESUME)
00:02  CDC terminé (~2 min de traitement)
00:03  WH se suspend (AUTO_SUSPEND après 60s d'inactivité)
       ...
       WH dort pendant ~7 min (0 crédit)
       ...
00:10  Prochain CDC → WH se réveille
```

Sur 10 min d'intervalle : **3 min facturées**, **7 min à 0 crédit** (30% actif / 70% endormi).

### Mode nuit (21h - 07h) : cycles réduits

```
21:00  ████████████████████████████  Dernier cycle complet (CDC + dbt)
21:40  ✓ Données fraîches soirée

       Le warehouse dort (~3h, 0 crédit)

00:30  ██  1 CDC seul (vider le backlog Kafka avant ref_reload)

01:00  ████████████████████████████████████████████████  ref_reload 14 tables
       │                                                  (séquentiel, ~3h31 cumulées)
       │
       │  01:00 → 01:03  RAW_PHARMACIE, LOG, PHARMACIES          (3 min)
       │  01:03 → 01:06  RAW_FOURNISSEURS, HISTORY               (3 min)
       │  01:06 → 01:08  RAW_LPPR                                (2 min)
       │  01:08 → 01:14  RAW_EAN13                               (6 min)
       │  01:14 → 01:24  RAW_PRODUITS                           (10 min)
       │  01:24 → 01:52  RAW_DAYBYDAY                           (28 min)
       │  01:52 → 02:28  RAW_ORDERS                             (36 min)
       │  02:28 → 04:31  RAW_MEDIPRIX_FACTURES                (2h03 min)
       │
~04:00-04:30  Fin ref_reload

04:30  ████████████████████████████  1 CDC + 1 cycle dbt complet
~05:10-05:30  ✓ Données fraîches matin

       Le warehouse dort (~1h30, 0 crédit)

07:00  Reprise rythme jour
```

[↑ Retour au sommaire](#table-des-matières)

---

## 4. Récapitulatif 24h

  ┌──────────────────────┬────────┬─────────────┬─────────────┬────────────────────────────┐
  │ Tranche              │ Durée  │ Cycles CDC  │ Cycles dbt  │ Warehouse                  │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Jour (07h-21h)       │ 14h    │ 84          │ 14          │ ~9.9h actif                │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Soir (21h-21h40)     │ 40 min │ 1           │ 1           │ ~40 min actif              │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Nuit calme           │ ~3h    │ 0           │ 0           │ dort                       │
  │ (21h40-00h30)        │        │             │             │                            │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ CDC pré-reload       │ ~2 min │ 1           │ 0           │ ~3 min actif               │
  │ (00h30)              │        │             │             │                            │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Ref_reload           │ ~3h30  │ 0           │ 0           │ ~3.5h actif                │
  │ (01h-~04h30)         │        │             │             │                            │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Cycle matin          │ ~40min │ 1           │ 1           │ ~40 min actif              │
  │ (04h30-~05h10)       │        │             │             │                            │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ Nuit calme           │ ~1h50  │ 0           │ 0           │ dort                       │
  │ (05h10-07h)          │        │             │             │                            │
  ├──────────────────────┼────────┼─────────────┼─────────────┼────────────────────────────┤
  │ **Total 24h**        │        │ **87**      │ **16**      │ **~14.8h actif**           │
  │                      │        │             │             │ **~9.2h dort**             │
  └──────────────────────┴────────┴─────────────┴─────────────┴────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 5. Comparaison des coûts

Infrastructure Snowflake :
- Édition : **Enterprise**, région **AWS EU West 3 (Paris)**
- Warehouse : XSMALL (1 crédit/heure actif, 0 à l'arrêt)
- Tarif compute : **$3.00/crédit** (~2.76 EUR/crédit)
- Tarif stockage : **$24/TB/mois** (~22.08 EUR/TB/mois)
- Source : `SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY` (30 mars 2026)

### Avant vs Après (compute)

  ┌──────────────────────────────┬─────────────┬──────────────┬──────────────┬──────────┐
  │ Scénario                     │ Crédits/jour│ EUR/mois     │ EUR/an       │ Économie │
  ├──────────────────────────────┼─────────────┼──────────────┼──────────────┼──────────┤
  │ Avant : boucle monolithique  │ 23.4        │ 1 937 EUR    │ 23 244 EUR   │ —        │
  │ 30 min, 24/7                 │             │              │              │          │
  ├──────────────────────────────┼─────────────┼──────────────┼──────────────┼──────────┤
  │ Après : CDC 10min, dbt 1h,   │ 15.3        │ 1 268 EUR    │ 15 418 EUR   │ -35%     │
  │ nuit réduite, WH se suspend  │             │              │              │          │
  └──────────────────────────────┴─────────────┴──────────────┴──────────────┴──────────┘

### Stockage (mesuré le 30 mars 2026)

  ┌──────────────────────┬──────────┬──────────────┬──────────────┬──────────┐
  │ Database             │ GB       │ EUR/mois     │ EUR/an       │ Note     │
  ├──────────────────────┼──────────┼──────────────┼──────────────┼──────────┤
  │ MEDICORE_PROD        │ 67       │ 1.48         │ 18           │ Données  │
  │                      │          │              │              │ réelles  │
  ├──────────────────────┼──────────┼──────────────┼──────────────┼──────────┤
  │ MEDICORE_DEV         │ 120      │ 2.65         │ 32           │ Clone +  │
  │ (+ 118 Time Travel)  │ (+118)   │ (+2.60)      │ (+31)        │ modifs   │
  ├──────────────────────┼──────────┼──────────────┼──────────────┼──────────┤
  │ MEDICORE_TEST        │ ~0       │ 0            │ 0            │ Seeds    │
  ├──────────────────────┼──────────┼──────────────┼──────────────┼──────────┤
  │ Failsafe             │ 15       │ 0.33         │ 4            │ Auto     │
  ├──────────────────────┼──────────┼──────────────┼──────────────┼──────────┤
  │ **Total stockage**   │ **~320** │ **~5 EUR**   │ **~60 EUR**  │          │
  └──────────────────────┴──────────┴──────────────┴──────────────┴──────────┘

### Détail de l'économie (compute)

  ┌──────────────────────────────────────────────┬──────────────────────────────────────┐
  │ Poste d'économie                             │ Gain                                 │
  ├──────────────────────────────────────────────┼──────────────────────────────────────┤
  │ Nuit : 14 cycles dbt supprimés               │ ~4.5h WH/nuit                        │
  ├──────────────────────────────────────────────┼──────────────────────────────────────┤
  │ Jour : WH se suspend entre les CDC           │ ~4.1h WH/jour (14h → 9.9h actif)    │
  ├──────────────────────────────────────────────┼──────────────────────────────────────┤
  │ Skip dbt quand 0 event CDC                   │ Variable (évite ~35 min/cycle vide)  │
  ├──────────────────────────────────────────────┼──────────────────────────────────────┤
  │ **Économie compute annuelle**                │ **~7 800 EUR**                       │
  └──────────────────────────────────────────────┴──────────────────────────────────────┘

### Coût total annuel MediCore

  ┌────────────────────────┬──────────────┬──────────┐
  │ Poste                  │ EUR/an       │ %        │
  ├────────────────────────┼──────────────┼──────────┤
  │ Compute (orch. V2)     │ 15 418       │ 99.6%    │
  ├────────────────────────┼──────────────┼──────────┤
  │ Stockage               │ ~60          │ 0.4%     │
  ├────────────────────────┼──────────────┼──────────┤
  │ **Total**              │ **~15 478**  │          │
  └────────────────────────┴──────────────┴──────────┘

Le stockage est négligeable (0.4% du coût total). L'optimisation du
compute via l'orchestration V2 génère l'essentiel de l'économie.

[↑ Retour au sommaire](#table-des-matières)

---

## 6. Pourquoi cette stratégie est adéquate pour MediCore

### Alignement avec le métier pharmacie

Les pharmacies ont un rythme d'activité prévisible : ouverture 08h-20h,
avec des pics matin et après-midi. La nuit, aucune transaction n'est générée.
La stratégie **épouse ce rythme** au lieu de traiter uniformément 24/7.

### Fraîcheur adaptée aux usages

Un pharmacien qui consulte son tableau de bord des ventes du jour à 10h
n'a pas besoin de voir la dernière ordonnance entrée il y a 2 minutes.
Un refresh toutes les **heures** est imperceptible pour des KPIs
**journaliers**. En revanche, l'ingestion CDC toutes les **10 minutes**
garantit que les données brutes sont toujours proches du temps réel.

### Données prêtes avant l'ouverture

En avançant le ref_reload de 03h à **01h**, les 14 tables de référence
(~463M lignes, ~3h-3h30 de chargement) sont rechargées et intégrées par
dbt avant **05h30**. À l'arrivée du premier utilisateur à 07h-08h,
les dashboards affichent des données complètes et à jour.

### Économie sans compromis fonctionnel

La réduction de **35%** des coûts Snowflake (~5 200 EUR/an) est obtenue
uniquement en éliminant le travail inutile : cycles nocturnes sans
utilisateur, dbt sur des données inchangées, warehouse allumé sans requête.
**Aucune fonctionnalité n'est dégradée.**

### Évolutivité vers un orchestrateur

La séparation CDC / dbt / ref_reload en fonctions distinctes (`run_cdc()`,
`run_dbt()`) prépare la migration future vers un orchestrateur (Airflow,
Dagster). Chaque fonction deviendra une tâche dans un DAG, avec sa propre
fréquence et ses retries. `batch_loop.sh` sera alors supprimé sans refactoring
des phases individuelles.

[↑ Retour au sommaire](#table-des-matières)

---

## 7. Variables de configuration

Toutes les variables sont surchargeables via l'environnement (.env) :

  ┌────────────────────────────┬───────────────┬───────────────┬──────────────────────────┐
  │ Variable                   │ Défaut prod   │ Défaut dev    │ Rôle                     │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ CDC_INTERVAL_MIN           │ 10            │ 2             │ Intervalle entre CDC     │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ DBT_EVERY_N                │ 6 (~60 min)   │ 3 (~6 min)    │ dbt toutes les N         │
  │                            │               │               │ itérations CDC           │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ NIGHT_START / NIGHT_END    │ 19 / 5 (UTC)  │ 19 / 5 (UTC)  │ 21h-07h FR (UTC+2)       │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ REF_RELOAD_HOUR            │ 21 (UTC)      │ 21 (UTC)      │ 23h FR, CLONE+SWAP       │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ REF_TIMEOUT_SEC            │ 18000 (5h)    │ 18000         │ Timeout ref_reload       │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ POST_RELOAD_DBT_HOUR/MIN   │ 04:30         │ 04:30         │ Cycle dbt post-reload    │
  ├────────────────────────────┼───────────────┼───────────────┼──────────────────────────┤
  │ PHASE_TIMEOUT_SEC          │ 1800 (30 min) │ 1800          │ Timeout par phase dbt    │
  └────────────────────────────┴───────────────┴───────────────┴──────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 8. Temps mesurés (ref_reload, 25 mars 2026)

  ┌────────────────────────────────┬────────────────┬──────────────┬──────────────────────┐
  │ Table                          │ Lignes         │ Temps total  │ Source               │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_MEDIPRIX_FACTURES          │ 258 219 783    │ ~2h03        │ Mesuré               │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_ORDERS                     │ 60 102 010     │ ~36 min      │ Mesuré               │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_DAYBYDAY                   │ 44 653 451     │ ~28 min      │ Estimation (ratio)   │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_PRODUITS                   │ 9 448 231      │ ~10 min      │ Estimation (ratio)   │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_EAN13                      │ 8 913 086      │ ~6 min       │ Estimation (ratio)   │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ RAW_LPPR                       │ 1 220 818      │ ~2 min       │ Estimation (ratio)   │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ 8 petites tables               │ < 1 000 000    │ ~8 min       │ Overhead fixe        │
  ├────────────────────────────────┼────────────────┼──────────────┼──────────────────────┤
  │ **Total ref_reload**           │ **~463M**      │ **~3h-3h30** │                      │
  └────────────────────────────────┴────────────────┴──────────────┴──────────────────────┘

Débit observé : **~1.7 — 2.1 millions de lignes/min** (goulot : extraction MySQL,
pas Snowflake).

[↑ Retour au sommaire](#table-des-matières)

---

## Voir aussi

- [Opérations](03_operations.md) — guide opérationnel complet et monitoring
