# KPIs MediCore — Documentation complète

Ce document recense l'ensemble des indicateurs clés de performance (KPIs) calculés par les modèles dbt de la couche MARTS, ainsi que les KPIs non réalisables aujourd'hui et les actions à mener pour les rendre disponibles.

---

## Table des matières

1. [KPIs des tables de faits](#1-kpis-des-tables-de-faits)
   - [fact_ventes](#11-fact_ventes--ventes-quotidiennes)
   - [fact_commandes](#12-fact_commandes--achats-fournisseurs)
   - [fact_prix_journalier](#13-fact_prix_journalier--évolution-des-prix)
   - [fact_stock_mouvement](#14-fact_stock_mouvement--mouvements-de-stock)
2. [KPIs croisés](#2-kpis-croisés)
   - [mart_kpi_marge](#21-mart_kpi_marge--marge-journalière)
   - [mart_kpi_stock](#22-mart_kpi_stock--rotation-et-rupture-mensuelles)
   - [mart_kpi_ecoulement](#23-mart_kpi_ecoulement--taux-découlement-mensuel)
3. [Axes d'analyse (dimensions)](#3-axes-danalyse-dimensions)
4. [KPIs manquants et plan d'action](#4-kpis-manquants-et-plan-daction)

---

## 1. KPIs des tables de faits

### 1.1 fact_ventes — Ventes quotidiennes

Table agrégée par pharmacie, produit et jour. Chaque ligne représente le total des ventes d'un produit dans une pharmacie pour une journée donnée.

  ┌───────────────┬────────────────────────────┬─────────────────────────────────────┐
  │      KPI      │          Formule           │           Exemple concret           │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ Chiffre d'affaires hors taxes.      │
  │               │                            │ La pharmacie Dupont a vendu pour 1  │
  │               │                            │ 250 EUR HT de Doliprane 1000mg en   │
  │ CA HT         │ sum(ca_ht)                 │ janvier. C'est la somme de toutes   │
  │               │                            │ les lignes de factures HT pour ce   │
  │               │                            │ produit ce mois-là.                 │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ Chiffre d'affaires toutes taxes     │
  │               │                            │ comprises (HT + TVA).               │
  │ CA TTC        │ sum(ca_ttc)                │ Le même Doliprane a généré 1 500    │
  │               │                            │ EUR TTC (HT + TVA).                 │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ Nombre total d'unités vendues.      │
  │               │                            │ 500 boîtes de Doliprane vendues en  │
  │ Quantités     │ sum(quantite_vendue)       │ janvier. On additionne les          │
  │ vendues       │                            │ quantités de chaque ligne de        │
  │               │                            │ facture.                            │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ nombre de passages en caisse.       │
  │               │                            │ Ces 500 boîtes sont réparties sur   │
  │ Nb lignes de  │ sum(nb_lignes)             │ 320 passages en caisse (lignes de   │
  │ vente         │                            │ facturation). Un client peut        │
  │               │                            │ acheter 2 boîtes = 1 ligne.         │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ La TVA moyenne sur ce produit est   │
  │ TVA moyenne   │ avg(tva_moyenne)           │ de 2.1% (taux réduit médicaments).  │
  │               │                            │ C'est la moyenne arithmétique des   │
  │               │                            │ taux TVA de chaque ligne.           │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ La remise la plus élevée accordée   │
  │ Remise max    │ max(remise_max)            │ sur Doliprane ce mois-ci est 15%    │
  │               │                            │ (peut-être une promo).              │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ CA TTC moyen par jour d'activité    │
  │               │                            │ pour un produit.                    │
  │Panier moyen   │ sum(ca_ttc) /              │ 1 500 EUR / 25 jours d'ouverture =  │
  │               │ count(distinct date_vente) │ 60 EUR/jour de Doliprane en         │
  │               │                            │ moyenne.                            │
  ├───────────────┼────────────────────────────┼─────────────────────────────────────┤
  │               │                            │ Sur les 500 boîtes : 200 vendues à  │
  │ Segmentation  │ ventilation par            │ des femmes 30-50 ans, 150 à des     │
  │ client        │ ORD_CLIENT_AGE_MONTHS,     │ hommes 50-70 ans, etc. Permet       │
  │               │ ORD_CLIENT_SEX             │ d'analyser qui achète quoi,         │
  │               │                            │ par tranche d'âge et sexe.          │
  └───────────────┴────────────────────────────┴─────────────────────────────────────┘


### 1.2 fact_commandes — Achats fournisseurs

Table agrégée par pharmacie, produit, fournisseur, jour et numéro de commande. Chaque ligne représente une commande passée à un fournisseur.

  ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
  │      KPI       │         Formule         │            Exemple concret            │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Montant        │                         │ La pharmacie a commandé pour 800 EUR  │
  │ commandé (PAHT │ sum(montant_pahtnet)    │ PAHT net de Doliprane chez OCP en     │
  │  net)          │                         │ janvier. C'est le prix d'achat hors   │
  │                │                         │ taxes après remises.                  │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ nombre total d'unités commandées au   │
  │ Quantités      │                         │ fournisseur.                          │
  │ commandées     │ sum(quantite_commandee) │ 600 boîtes commandées (on commande    │
  │                │                         │ plus qu'on ne vend pour maintenir du  │
  │                │                         │ stock).                               │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Remise         │                         │ Le fournisseur OCP accorde en moyenne │
  │ fournisseur    │ avg(remise_moyenne)     │ 12% de remise sur Doliprane. C'est    │
  │ moyenne        │                         │ la moyenne des taux de remise de      │
  │                │                         │ chaque ligne de commande.             │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Nombre de commandes distinctes        │
  │ Nb commandes   │ count(distinct          │ passées dans la période.              │
  │                │ commande_id)            │ 8 commandes passées dans le mois      │
  │                │                         │ (environ 2 par semaine).              │
  └────────────────┴─────────────────────────┴───────────────────────────────────────┘


### 1.3 fact_prix_journalier — Évolution des prix

Table au grain journalier par pharmacie et produit. Chaque ligne contient les 4 prix du produit pour un jour donné, ainsi que la marge unitaire calculée.

  ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
  │      KPI       │         Formule         │            Exemple concret            │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Prix catalogue officiel du produit.   │
  │ Prix tarif     │ prix_tarif              │ Le prix catalogue du Doliprane est    │
  │                │                         │ 3.00 EUR au 15 janvier                │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Le prix affiché en rayon est 3.10 EUR │
  │ Prix public    │ prix_public             │ (le pharmacien peut majorer           │
  │                │                         │ légèrement).                          │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Prix d'achat moyen pondéré.           │
  │                │                         │ Si le pharmacien a acheté 100 boîtes  │
  │ PAMP           │ prix_achat_moyen_pondere│ de Doliprane à 1.70 EUR et 100 autres │
  │                │                         │ à 1.90 EUR, le PAMP = ((100 x 1.70) + │
  │                │                         │ (100 x 1.90)) / 200 = 1.80 EUR.       │ 
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Le dernier prix d'achat réel après    │
  │ Prix d'achat   │ prix_achat_net          │ toutes les remises fournisseur est    │
  │ net            │                         │ 1.65 EUR.                             │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Marge brute    │ prix_public -           │ Marge réalisée sur chaque unité       │
  │ unitaire       │ prix_achat_net          │ vendue, indépendamment de la quantité.│
  │                │                         │ 3.10 - 1.65 = 1.45 EUR de marge/boîte.│
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Part de marge dans le prix public     │
  │ Taux de marge  │  (prix_public -         │ Permet de comparer la rentabilité     │
  │ unitaire       │  prix_achat_net) /      │ entre produits.                       │
  │                │  prix_public            │ 1.45 / 3.10 = 46.8% de taux de marge. │
  └────────────────┴─────────────────────────┴───────────────────────────────────────┘


### 1.4 fact_stock_mouvement — Mouvements de stock

Table au grain journalier par pharmacie et produit. Chaque ligne représente le résumé des mouvements de stock d'un produit pour un jour donné.

  ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
  │                │                         │ Variation nette du stock sur la       │
  │                │                         │ journée. Positif = entrée (réception, │
  │ Delta stock    │ sum(delta_stock)        │ inventaire), négatif = sortie (vente, │
  │                │                         │ casse).                               │
  │                │                         │ Le 15 janvier, le Doliprane a eu +50  │ 
  │                │                         │ (réception) puis -3 (ventes) = delta  │ 
  │                │                         │ de +47 boîtes                         │ 
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Quantité en stock après le dernier    │
  │ Stock après    │ stock_apres             │ mouvement de la journée.              │
  │ mouvement      │                         │ Après le dernier mouvement du 15      │
  │                │                         │ janvier, il reste 120 boîtes en stock.│
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │ Type           │ type_operation          │ Nature du mouvement (entrée, sortie,  │
  │ d'opération    │                         │ inventaire, etc.).                    │
  │                │                         │ Le mouvement est de type "E" (entrée) │
  │                │                         │ ou "S" (sortie) ou "I" (inventaire).  │
  └────────────────┴─────────────────────────┴───────────────────────────────────────┘


## 2. KPIs croisés

Ces modèles croisent plusieurs tables de faits entre elles pour calculer des indicateurs qu'aucune table seule ne peut fournir.

### 2.1 mart_kpi_marge — Marge journalière

**Croisement** : `fact_ventes` x `fact_prix_journalier` sur la même pharmacie + même produit + même date.

**Logique** : on prend les quantités et le CA réellement vendus, et on les rapproche du prix d'achat du jour pour calculer la marge totale en euros.

**Grain** : pharmacie, produit, jour.

  ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
  │                │                         │ Coût total d'achat des unités         │
  │                │                         │ effectivement vendues ce jour-là.     │
  │ Coût d'achat   │ quantite_vendue ×       │ 20 boîtes vendues x 1.65 EUR = 33 EUR │
  │ net            │ prix_achat_net          │ de coût d'achat                       │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Bénéfice brut de la journée pour      │
  │ Marge brute    │ ca_ht - cout_achat_net  │ ce produit.                           │
  │                │                         │ Le CA HT du jour est 60 EUR           │
  │                │                         │ (20 boîtes × 3 EUR HT).               │
  │                │                         │ 60 EUR de CA HT - 33 EUR de coût =    │
  │                │                         │ 27 EUR de marge brute.                │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Part de marge dans le CA HT.          │
  │ Taux de marge  │ marge_brute / ca_ht     │ Permet de comparer la rentabilité     │
  │                │                         │ entre produits et entre jours.        │
  │                │                         │ 27 / 60 = 45%. Sur chaque euro de     │
  │                │                         │ vente HT, 45 centimes sont de la marge│
  └────────────────┴─────────────────────────┴───────────────────────────────────────┘

  **Différence avec fact_prix_journalier** : `fact_prix_journalier` donne la marge **par boîte** (unitaire, indépendante des volumes). `mart_kpi_marge` donne la marge **totale** d'une journée en multipliant par les quantités réellement vendues.


### 2.2 mart_kpi_stock — Rotation et rupture mensuelles

**Croisement** : `fact_stock_mouvement` x `fact_ventes`, agrégés au mois.

**Logique** : on calcule le stock moyen du mois à partir des mouvements, puis on le rapproche des quantités vendues pour mesurer la vitesse d'écoulement du stock.

**Grain** : pharmacie, produit, mois.

| KPI | Formule |
|-----|---------|
| Stock moyen | `avg(stock_apres)` sur le mois |
| Stock min | `min(stock_apres)` |
| Stock max | `max(stock_apres)` |
| Nb jours rupture | Nombre de jours où `stock_apres = 0` |
| Taux de rupture | `nb_jours_rupture / nb_jours_mouvement` |
| Rotation de stock | `quantite_vendue / stock_moyen` |

**Explications et exemples :**

- **Stock moyen** : niveau de stock moyen constaté dans le mois.
  *Exemple : en janvier, stocks de 120, 80, 150 sur 3 relevés, stock moyen = 116 boîtes.*

- **Stock min / max** : stock le plus bas et le plus haut atteints dans le mois.
  *Exemple : stock le plus bas = 80 boîtes, le plus haut = 150 boîtes.*

- **Nb jours rupture** : nombre de jours où le produit était indisponible (stock à zéro).
  *Exemple : le stock est tombé à 0 pendant 2 jours (le 10 et le 11 janvier).*

- **Taux de rupture** : proportion de jours en rupture par rapport aux jours d'activité. Un taux élevé signale un problème d'approvisionnement.
  *Exemple : 2 jours de rupture / 20 jours de mouvement = 10% de taux de rupture.*

- **Rotation de stock** : nombre de fois que le stock "tourne" dans le mois. Plus c'est élevé, plus le produit se vend vite. Une rotation faible indique un sur-stockage.
  *Exemple : 500 boîtes vendues / 116 en stock moyen = 4.3 rotations.*

---

### 2.3 mart_kpi_ecoulement — Taux d'écoulement mensuel

**Croisement** : `fact_commandes` x `fact_ventes`, agrégés au mois.

**Logique** : on compare ce que la pharmacie a commandé à ses fournisseurs avec ce qu'elle a effectivement vendu, pour mesurer l'adéquation approvisionnement/demande.

**Grain** : pharmacie, produit, mois.

| KPI | Formule |
|-----|---------|
| Quantité commandée | `sum(quantite_commandee)` |
| Montant commandé | `sum(montant_pahtnet)` |
| Nb commandes | `count(distinct commande_id)` |
| Quantité vendue | `sum(quantite_vendue)` |
| CA HT | `sum(ca_ht)` |
| Taux d'écoulement | `quantite_vendue / quantite_commandee` |

**Explications et exemples :**

- **Quantité commandée** : total des unités commandées aux fournisseurs dans le mois.
  *Exemple : en janvier, 600 boîtes de Doliprane commandées.*

- **Montant commandé** : coût total des commandes du mois (PAHT net).
  *Exemple : coût total des commandes = 990 EUR PAHT.*

- **Nb commandes** : nombre de commandes distinctes passées dans le mois.
  *Exemple : 8 commandes dans le mois.*

- **Quantité vendue** : total des unités vendues dans le mois.
  *Exemple : 500 boîtes vendues.*

- **CA HT** : chiffre d'affaires HT des ventes du mois.
  *Exemple : 1 250 EUR HT de ventes.*

- **Taux d'écoulement** : rapport entre ce qui est vendu et ce qui est commandé.
  *Exemple : 500 / 600 = 83%.*

**Interprétation du taux d'écoulement :**

- **Inférieur à 100%** : on commande plus qu'on ne vend, le stock augmente. Normal si réapprovisionnement préventif, problématique si chronique.
- **Égal à 100%** : parfait équilibre entre offre et demande.
- **Supérieur à 100%** : on vend plus qu'on ne commande ce mois-là, on écoule du stock antérieur. Risque de rupture à terme.

---

## 3. Axes d'analyse (dimensions)

Tous les KPIs ci-dessus peuvent être filtrés et ventilés selon les axes suivants :

| Dimension | Colonnes disponibles |
|-----------|---------------------|
| dim_pharmacie | PHA_NOM, external_city, postal_code, PHA_GERS |
| dim_produit | PRD_NOM, EAN13, PRD_CODEREMBT, PRD_CODEACTE, LPP_CODE, PRD_TVA |
| dim_fournisseur | FOU_NOM, FOU_VILLE, FOU_TYPE, FOU_REPARTITEUR |
| Temporel | date_vente, date_commande, date_prix, date_mouvement, mois |

**Exemples d'analyses possibles :**

- CA par pharmacie, par ville, par zone géographique
- Marge par famille de produit, analyse par code remboursement
- Performance par fournisseur, comparaison entre répartiteurs
- Évolution mensuelle, saisonnalité, tendances

---

## 4. KPIs manquants et plan d'action

Deux KPIs ne sont pas calculables aujourd'hui car les données sources nécessaires n'existent pas dans le pipeline.

### 4.1 Délai d'approvisionnement

**Définition** : temps écoulé entre la date de commande au fournisseur et la date de réception effective de la marchandise à la pharmacie.

**Formule cible** : `delai_moyen = avg(date_reception - date_commande)` en jours.

**Exemple concret** : une commande passée le 5 janvier et reçue le 7 janvier a un délai de 2 jours. Si le fournisseur OCP a un délai moyen de 1.5 jours et Alliance de 2.8 jours, on sait qu'OCP est plus rapide.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la date de commande (`COM_DATE` dans la table `COMMANDES`), mais aucune table source ne contient la date de réception.

### 4.2 Taux de service fournisseur

**Définition** : rapport entre la quantité effectivement livrée par le fournisseur et la quantité commandée.

**Formule cible** : `taux_service = quantite_recue / quantite_commandee`.

**Exemple concret** : on commande 100 boîtes de Doliprane, le fournisseur en livre 95. Le taux de service est de 95%. Un fournisseur en dessous de 90% pose un problème de fiabilité.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la quantité commandée (`COM_QUANTITE` dans la table `COMMANDES`), mais aucune table source ne contient la quantité effectivement reçue.

### 4.3 Solution : table source à intégrer

Les deux KPIs manquants nécessitent la même donnée : **les réceptions de marchandise**. Il faudrait intégrer une table `RECEPTIONS` (ou `LIVRAISONS`) depuis le logiciel de gestion d'officine (LGO) dans le pipeline CDC.

**Structure minimale requise de la table source MySQL :**

```
RECEPTIONS
├── PHA_ID           INT          -- Identifiant pharmacie
├── COM_GROI         VARCHAR      -- N° de commande (jointure avec COMMANDES)
├── FOU_ID           INT          -- Identifiant fournisseur
├── PRD_ID           INT          -- Identifiant produit
├── REC_DATE         DATETIME     -- Date de réception effective
├── REC_QUANTITE     INT          -- Quantité réellement reçue
└── REC_STATUT       VARCHAR      -- Statut (complète, partielle, refusée)
```

**Étapes d'intégration dans le pipeline :**

1. **CDC (Debezium)** : ajouter un connecteur pour la table `RECEPTIONS` dans la configuration Debezium, pour capter les insertions/modifications en temps réel.

2. **Kafka** : un nouveau topic `medicore.RECEPTIONS` sera automatiquement créé par Debezium.

3. **Snowflake RAW** : configurer le Snowflake Sink Connector pour consommer ce topic et alimenter une table `RAW.RECEPTIONS`.

4. **dbt staging** : créer un modèle `stg_receptions.sql` (matérialisation incremental merge) pour nettoyer et typer les données.

5. **dbt marts** : créer un modèle `mart_kpi_approvisionnement.sql` croisant `fact_commandes` avec `stg_receptions`.

**Exemple de structure du futur modèle :**

```sql
select
    c.pharmacie_sk,
    c.produit_sk,
    c.fournisseur_sk,
    c.date_commande,
    r.date_reception,
    datediff('day', c.date_commande, r.date_reception) as delai_jours,
    c.quantite_commandee,
    r.quantite_recue,
    r.quantite_recue / nullif(c.quantite_commandee, 0) as taux_service
from fact_commandes c
inner join stg_receptions r
    on c.pharmacie_sk = r.pharmacie_sk
    and c.commande_id = r.commande_id
    and c.produit_sk = r.produit_sk
```

**KPIs qui deviendraient alors disponibles :**

| KPI | Formule |
|-----|---------|
| Délai d'approvisionnement | `avg(date_reception - date_commande)` |
| Taux de service | `sum(quantite_recue) / sum(quantite_commandee)` |
| Taux de livraison complète | `count(réceptions complètes) / count(commandes)` |

**Exemples :**

- OCP livre en moyenne en 1.5 jours
- OCP livre 97% des quantités commandées
- 92% des commandes OCP arrivent complètes
