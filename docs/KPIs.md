# KPIs MediCore — Documentation complète

Ce document recense l'ensemble des indicateurs clés de performance (KPIs) calculés par les modèles dbt de la couche MARTS, ainsi que les KPIs non réalisables aujourd'hui et les actions à mener pour les rendre disponibles.

---

## Table des matières

1. [KPIs des tables de faits](#1-kpis-des-tables-de-faits)
   - [fact_ventes — Ventes quotidiennes](#11-fact_ventes--ventes-quotidiennes)
   - [fact_commandes — Achats fournisseurs](#12-fact_commandes--achats-fournisseurs)
   - [fact_prix_journalier — Évolution des prix](#13-fact_prix_journalier--évolution-des-prix)
   - [fact_stock_mouvement — Mouvements de stock](#14-fact_stock_mouvement--mouvements-de-stock)
2. [KPIs croisés](#2-kpis-croisés)
   - [mart_kpi_marge — Marge journalière](#21-mart_kpi_marge--marge-journalière)
   - [mart_kpi_stock — Rotation et rupture](#22-mart_kpi_stock--rotation-et-rupture-mensuelles)
   - [mart_kpi_ecoulement — Taux d'écoulement](#23-mart_kpi_ecoulement--taux-découlement-mensuel)
3. [Axes d'analyse (dimensions)](#3-axes-danalyse-dimensions)
4. [KPIs manquants et plan d'action](#4-kpis-manquants-et-plan-daction)

---

## 1. KPIs des tables de faits

### 1.1 fact_ventes — Ventes quotidiennes

Table agrégée par pharmacie, produit et jour. Chaque ligne représente le total des ventes d'un produit dans une pharmacie pour une journée donnée.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **CA HT** | `sum(ca_ht)` | Chiffre d'affaires hors taxes. Somme des montants HT de toutes les lignes de factures. | La pharmacie Dupont a vendu pour **1 250 EUR HT** de Doliprane 1000mg en janvier. |
| **CA TTC** | `sum(ca_ttc)` | Chiffre d'affaires toutes taxes comprises (HT + TVA). | Le même Doliprane a généré **1 500 EUR TTC**. |
| **Quantités vendues** | `sum(quantite_vendue)` | Nombre total d'unités vendues. On additionne les quantités de chaque ligne de facture. | **500 boîtes** de Doliprane vendues en janvier. |
| **Nb lignes de vente** | `sum(nb_lignes)` | Nombre de passages en caisse (lignes de facturation). Un client peut acheter plusieurs boîtes en une seule ligne. | Ces 500 boîtes sont réparties sur **320 passages en caisse**. |
| **TVA moyenne** | `avg(tva_moyenne)` | Moyenne arithmétique des taux de TVA appliqués sur chaque ligne de vente. | La TVA moyenne sur Doliprane est de **2.1%** (taux réduit médicaments). |
| **Remise max** | `max(remise_max)` | Remise la plus élevée accordée sur un produit dans la période. | La remise la plus élevée sur Doliprane ce mois-ci est **15%** (promo). |
| **Panier moyen** | `sum(ca_ttc) / count(distinct date_vente)` | CA TTC moyen par jour d'activité pour un produit. | 1 500 EUR / 25 jours = **60 EUR/jour** de Doliprane en moyenne. |
| **Segmentation client** | Ventilation par `ORD_CLIENT_AGE_MONTHS` et `ORD_CLIENT_SEX` | Analyse de qui achète quoi, par tranche d'âge et sexe. | Sur 500 boîtes : **200** vendues à des femmes 30-50 ans, **150** à des hommes 50-70 ans. |

---

### 1.2 fact_commandes — Achats fournisseurs

Table agrégée par pharmacie, produit, fournisseur, jour et numéro de commande. Chaque ligne représente une commande passée à un fournisseur.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Montant commandé (PAHT net)** | `sum(montant_pahtnet)` | Prix d'achat hors taxes après remises fournisseur. | La pharmacie a commandé pour **800 EUR PAHT net** de Doliprane chez OCP en janvier. |
| **Quantités commandées** | `sum(quantite_commandee)` | Nombre total d'unités commandées au fournisseur. | **600 boîtes** commandées (plus que les ventes pour maintenir du stock). |
| **Remise fournisseur moyenne** | `avg(remise_moyenne)` | Moyenne des taux de remise accordés par le fournisseur sur chaque ligne de commande. | OCP accorde en moyenne **12%** de remise sur Doliprane. |
| **Nb commandes** | `count(distinct commande_id)` | Nombre de commandes distinctes passées dans la période. | **8 commandes** dans le mois (environ 2 par semaine). |

---

### 1.3 fact_prix_journalier — Évolution des prix

Table au grain journalier par pharmacie et produit. Chaque ligne contient les 4 prix du produit pour un jour donné, ainsi que la marge unitaire calculée.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Prix tarif** | `prix_tarif` | Prix catalogue officiel du produit. | Le prix catalogue du Doliprane est **3.00 EUR** au 15 janvier. |
| **Prix public** | `prix_public` | Prix affiché en rayon (le pharmacien peut ajuster légèrement). | Le prix en rayon est **3.10 EUR**. |
| **PAMP** | `prix_achat_moyen_pondere` | Prix d'achat moyen pondéré. Si le pharmacien a acheté 100 boîtes à 1.70 EUR et 100 à 1.90 EUR, le PAMP = (100×1.70 + 100×1.90) / 200. | Le PAMP du Doliprane est **1.80 EUR**. |
| **Prix d'achat net** | `prix_achat_net` | Dernier prix d'achat réel après toutes les remises fournisseur. | Le prix d'achat net est **1.65 EUR**. |
| **Marge brute unitaire** | `marge_brute_unitaire` = `prix_public - prix_achat_net` | Marge réalisée sur chaque unité vendue, indépendamment de la quantité. | 3.10 - 1.65 = **1.45 EUR** de marge par boîte. |
| **Taux de marge unitaire** | `taux_marge_unitaire` = `(prix_public - prix_achat_net) / prix_public` | Part de marge dans le prix public. Permet de comparer la rentabilité entre produits. | 1.45 / 3.10 = **46.8%** de taux de marge. |

---

### 1.4 fact_stock_mouvement — Mouvements de stock

Table au grain journalier par pharmacie et produit. Chaque ligne représente le résumé des mouvements de stock d'un produit pour un jour donné.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Delta stock** | `sum(delta_stock)` | Variation nette du stock sur la journée. Positif = entrée (réception, inventaire), négatif = sortie (vente, casse). | Le 15 janvier, le Doliprane a eu +50 (réception) puis -3 (ventes) = delta de **+47 boîtes**. |
| **Stock après mouvement** | `stock_apres` | Quantité en stock après le dernier mouvement de la journée. | Après le dernier mouvement du 15 janvier, il reste **120 boîtes** en stock. |
| **Type d'opération** | `type_operation` | Nature du mouvement (entrée, sortie, inventaire, etc.). | Le mouvement est de type **"E" (entrée)** ou **"S" (sortie)** ou **"I" (inventaire)**. |

---

## 2. KPIs croisés

Ces modèles croisent plusieurs tables de faits entre elles pour calculer des indicateurs qu'aucune table seule ne peut fournir.

### 2.1 mart_kpi_marge — Marge journalière

**Croisement** : `fact_ventes` × `fact_prix_journalier` sur la même pharmacie + même produit + même date.

**Logique** : on prend les quantités et le CA réellement vendus, et on les rapproche du prix d'achat du jour pour calculer la marge totale en euros.

**Grain** : pharmacie, produit, jour.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Coût d'achat net** | `cout_achat_net` = `quantite_vendue × prix_achat_net` | Coût total d'achat des unités effectivement vendues ce jour-là. | 20 boîtes vendues × 1.65 EUR = **33 EUR** de coût d'achat. |
| **Marge brute** | `marge_brute` = `ca_ht - cout_achat_net` | Bénéfice brut de la journée pour ce produit. | 60 EUR de CA HT - 33 EUR de coût = **27 EUR** de marge brute. |
| **Taux de marge** | `taux_marge` = `marge_brute / ca_ht` | Part de marge dans le CA HT. Permet de comparer la rentabilité entre produits et entre jours. | 27 / 60 = **45%**. Sur chaque euro de vente HT, 45 centimes sont de la marge. |

> **Différence avec `fact_prix_journalier`** : `fact_prix_journalier` donne la marge **par boîte** (unitaire, indépendante des volumes). `mart_kpi_marge` donne la marge **totale** d'une journée en multipliant par les quantités réellement vendues.

---

### 2.2 mart_kpi_stock — Rotation et rupture mensuelles

**Croisement** : `fact_stock_mouvement` × `fact_ventes`, agrégés au mois.

**Logique** : on calcule le stock moyen du mois à partir des mouvements, puis on le rapproche des quantités vendues pour mesurer la vitesse d'écoulement du stock.

**Grain** : pharmacie, produit, mois.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Stock moyen** | `stock_moyen` = `avg(stock_apres)` sur le mois | Niveau de stock moyen constaté dans le mois. | En janvier, stocks de 120, 80, 150 → stock moyen = **116 boîtes**. |
| **Stock min** | `stock_min` = `min(stock_apres)` | Stock le plus bas atteint dans le mois. | Stock le plus bas : **80 boîtes**. |
| **Stock max** | `stock_max` = `max(stock_apres)` | Stock le plus haut atteint dans le mois. | Stock le plus haut : **150 boîtes**. |
| **Nb jours rupture** | `nb_jours_rupture` = nombre de jours où `stock_apres = 0` | Nombre de jours où le produit était indisponible (stock à zéro). | Le stock est tombé à 0 pendant **2 jours** (le 10 et le 11 janvier). |
| **Taux de rupture** | `taux_rupture` = `nb_jours_rupture / nb_jours_mouvement` | Proportion de jours en rupture par rapport aux jours d'activité. Un taux élevé signale un problème d'approvisionnement. | 2 / 20 = **10%** de taux de rupture. |
| **Rotation de stock** | `rotation_stock` = `quantite_vendue / stock_moyen` | Nombre de fois que le stock "tourne" dans le mois. Plus c'est élevé, plus le produit se vend vite. Une rotation faible indique un sur-stockage. | 500 vendues / 116 en stock moyen = **4.3 rotations**. |

---

### 2.3 mart_kpi_ecoulement — Taux d'écoulement mensuel

**Croisement** : `fact_commandes` × `fact_ventes`, agrégés au mois.

**Logique** : on compare ce que la pharmacie a commandé à ses fournisseurs avec ce qu'elle a effectivement vendu, pour mesurer l'adéquation approvisionnement/demande.

**Grain** : pharmacie, produit, mois.

| KPI | Colonne / Formule | Description | Exemple concret |
|-----|--------------------|-------------|-----------------|
| **Quantité commandée** | `quantite_commandee` = `sum(quantite_commandee)` | Total des unités commandées aux fournisseurs dans le mois. | En janvier, **600 boîtes** de Doliprane commandées. |
| **Montant commandé** | `montant_commande` = `sum(montant_pahtnet)` | Coût total des commandes du mois (PAHT net). | Coût total des commandes : **990 EUR PAHT**. |
| **Nb commandes** | `nb_commandes` = `count(distinct commande_id)` | Nombre de commandes distinctes passées dans le mois. | **8 commandes** dans le mois. |
| **Quantité vendue** | `quantite_vendue` = `sum(quantite_vendue)` | Total des unités vendues dans le mois. | **500 boîtes** vendues. |
| **CA HT** | `ca_ht` = `sum(ca_ht)` | Chiffre d'affaires HT des ventes du mois. | **1 250 EUR HT** de ventes. |
| **Taux d'écoulement** | `taux_ecoulement` = `quantite_vendue / quantite_commandee` | Rapport entre ce qui est vendu et ce qui est commandé. | 500 / 600 = **83%**. |

> **Interprétation du taux d'écoulement** :
> - **< 100%** : on commande plus qu'on ne vend → le stock augmente (normal si réapprovisionnement préventif, problématique si chronique).
> - **= 100%** : parfait équilibre entre offre et demande.
> - **> 100%** : on vend plus qu'on ne commande ce mois-là → on écoule du stock antérieur, risque de rupture à terme.

---

## 3. Axes d'analyse (dimensions)

Tous les KPIs ci-dessus peuvent être filtrés et ventilés selon les axes suivants :

| Dimension | Colonnes disponibles | Exemple d'analyse |
|-----------|---------------------|-------------------|
| **dim_pharmacie** | PHA_NOM, external_city, postal_code, PHA_GERS | CA par pharmacie, par ville, par zone géographique |
| **dim_produit** | PRD_NOM, EAN13, PRD_CODEREMBT, PRD_CODEACTE, LPP_CODE, PRD_TVA | Marge par famille de produit, analyse par code remboursement |
| **dim_fournisseur** | FOU_NOM, FOU_VILLE, FOU_TYPE, FOU_REPARTITEUR | Performance par fournisseur, comparaison répartiteurs |
| **Temporel** | date_vente, date_commande, date_prix, date_mouvement, mois | Évolution mensuelle, saisonnalité, tendances |

---

## 4. KPIs manquants et plan d'action

Deux KPIs ne sont pas calculables aujourd'hui car les données sources nécessaires n'existent pas dans le pipeline.

### 4.1 Délai d'approvisionnement

**Définition** : temps écoulé entre la date de commande au fournisseur et la date de réception effective de la marchandise à la pharmacie.

**Formule cible** : `delai_moyen = avg(date_reception - date_commande)` en jours.

**Exemple concret** : une commande passée le 5 janvier et reçue le 7 janvier a un délai de **2 jours**. Si le fournisseur OCP a un délai moyen de 1.5 jours et Alliance de 2.8 jours, on sait qu'OCP est plus rapide.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la date de commande (`COM_DATE` dans `COMMANDES`), mais aucune table source ne contient la date de réception.

### 4.2 Taux de service fournisseur

**Définition** : rapport entre la quantité effectivement livrée par le fournisseur et la quantité commandée.

**Formule cible** : `taux_service = quantite_recue / quantite_commandee`.

**Exemple concret** : on commande 100 boîtes de Doliprane, le fournisseur en livre 95. Le taux de service est de **95%**. Un fournisseur en dessous de 90% pose un problème de fiabilité.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la quantité commandée (`COM_QUANTITE` dans `COMMANDES`), mais aucune table source ne contient la quantité effectivement reçue.

### 4.3 Solution : table source à intégrer

Les deux KPIs manquants nécessitent la même donnée : **les réceptions de marchandise**. Il faudrait intégrer une table `RECEPTIONS` (ou `LIVRAISONS`) depuis le logiciel de gestion d'officine (LGO) dans le pipeline CDC.

**Structure minimale requise de la table source MySQL** :

```
RECEPTIONS
├── PHA_ID           INT          -- Identifiant pharmacie
├── COM_GROI         VARCHAR      -- N° de commande (clé de jointure avec COMMANDES)
├── FOU_ID           INT          -- Identifiant fournisseur
├── PRD_ID           INT          -- Identifiant produit
├── REC_DATE         DATETIME     -- Date de réception effective
├── REC_QUANTITE     INT          -- Quantité réellement reçue
└── REC_STATUT       VARCHAR      -- Statut (complète, partielle, refusée)
```

**Étapes d'intégration dans le pipeline** :

1. **CDC (Debezium)** : ajouter un connecteur pour la table `RECEPTIONS` dans la configuration Debezium, pour capter les insertions/modifications en temps réel.

2. **Kafka** : un nouveau topic `medicore.RECEPTIONS` sera automatiquement créé par Debezium.

3. **Snowflake RAW** : configurer le Snowflake Sink Connector pour consommer ce topic et alimenter une table `RAW.RECEPTIONS`.

4. **dbt staging** : créer un modèle `stg_receptions.sql` (matérialisation incremental merge) pour nettoyer et typer les données.

5. **dbt marts** : créer un modèle `mart_kpi_approvisionnement.sql` croisant `fact_commandes` avec `stg_receptions` :

```sql
-- Exemple de structure du futur modèle
select
    c.pharmacie_sk,
    c.produit_sk,
    c.fournisseur_sk,
    c.date_commande,
    r.date_reception,
    datediff('day', c.date_commande, r.date_reception)   as delai_jours,
    c.quantite_commandee,
    r.quantite_recue,
    r.quantite_recue / nullif(c.quantite_commandee, 0)   as taux_service
from fact_commandes c
inner join stg_receptions r
    on c.pharmacie_sk = r.pharmacie_sk
    and c.commande_id = r.commande_id
    and c.produit_sk = r.produit_sk
```

**KPIs qui deviendraient alors disponibles** :

| KPI | Formule | Exemple |
|-----|---------|---------|
| Délai d'approvisionnement | `avg(date_reception - date_commande)` | OCP livre en moyenne en **1.5 jours** |
| Taux de service | `sum(quantite_recue) / sum(quantite_commandee)` | OCP livre **97%** des quantités commandées |
| Taux de livraison complète | `count(réceptions complètes) / count(commandes)` | **92%** des commandes OCP arrivent complètes |
