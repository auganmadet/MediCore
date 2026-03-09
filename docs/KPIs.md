# KPIs MediCore — Documentation complète

Ce document recense l'ensemble des indicateurs clés de performance (KPIs) calculés par les modèles dbt de la couche MARTS, ainsi que les KPIs non réalisables aujourd'hui et les actions à mener pour les rendre disponibles.

---

## Table des matières

1. [KPIs des tables de faits](#1-kpis-des-tables-de-faits)
   - [fact_ventes](#11-fact_ventes--ventes-quotidiennes)
   - [fact_commandes](#12-fact_commandes--achats-fournisseurs)
   - [fact_prix_journalier](#13-fact_prix_journalier--évolution-des-prix)
   - [fact_stock_mouvement](#14-fact_stock_mouvement--mouvements-de-stock)
   - [fact_ruptures](#15-fact_ruptures--ruptures-de-stock-demande-non-servie)
   - [fact_tresorerie](#16-fact_tresorerie--trésorerie-journalière)
   - [fact_stock_valorisation](#17-fact_stock_valorisation--stock-valorisé-quotidien)
   - [fact_operateur](#18-fact_operateur--ventes-par-opérateur)
2. [KPIs croisés](#2-kpis-croisés)
   - [mart_kpi_marge](#21-mart_kpi_marge--marge-journalière)
   - [mart_kpi_stock](#22-mart_kpi_stock--rotation-et-rupture-stock-mensuelles)
   - [mart_kpi_ecoulement](#23-mart_kpi_ecoulement--taux-découlement-mensuel)
   - [mart_kpi_ruptures](#24-mart_kpi_ruptures--impact-des-ruptures-et-ca-perdu)
   - [mart_kpi_tresorerie](#25-mart_kpi_tresorerie--trésorerie-mensuelle)
   - [mart_kpi_stock_valorisation](#26-mart_kpi_stock_valorisation--valorisation-et-couverture-stock)
   - [mart_kpi_qualite_donnees](#27-mart_kpi_qualite_donnees--monitoring-pipeline)
   - [mart_kpi_operateur](#28-mart_kpi_operateur--performance-opérateur)
   - [mart_kpi_abc](#29-mart_kpi_abc--classification-pareto)
3. [Axes d'analyse (dimensions)](#3-axes-danalyse-dimensions)
4. [Classification des KPIs par catégorie commerciale](#4-classification-des-kpis-par-catégorie-commerciale)
   - [Sell-in](#41-sell-in-achats-fournisseurs--pharmacie)
   - [Sell-out](#42-sell-out-pharmacie--consommateur-final)
   - [Sell-through](#43-sell-through-taux-découlement--rotation)
   - [Upsell](#44-upsell--upselling-montée-en-gamme)
   - [Cross-sell](#45-cross-sell--cross-selling-ventes-additionnelles)
   - [Downsell](#46-downsell--down-selling-substitution-vers-moins-cher)
   - [Repeat / Réachat](#47-repeat--réachat)
   - [Churn](#48-churn-attrition-client)
   - [CLV / LTV](#49-clv--ltv-customer-lifetime-value)
   - [Attach rate](#410-attach-rate-taux-dassociation-produits)
   - [Synthèse de couverture](#411-synthèse-de-couverture)
5. [KPIs manquants et plan d'action](#5-kpis-manquants-et-plan-daction)

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


### 1.5 fact_ruptures — Ruptures de stock (demande non servie)

Table au grain journalier par pharmacie et produit. Chaque ligne représente les ruptures constatées pour un produit dans une pharmacie pour un jour donné. Source : table `MANQHISTORY` (historique des manquants).

  ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
  │      KPI       │         Formule         │            Exemple concret            │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Nombre de lignes de commande client   │
  │ Nb lignes      │                         │ qui n'ont pas pu être satisfaites.    │
  │ manquantes     │ sum(nb_lignes_          │ 12 clients ont demandé du Doliprane   │
  │                │     manquantes)         │ le 15 janvier mais la pharmacie       │
  │                │                         │ n'en avait plus en stock.             │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Nombre total d'unités (boîtes) qui    │
  │ Nb boîtes      │ sum(nb_boites_          │ n'ont pas pu être délivrées.          │
  │ manquantes     │     manquantes)         │ Ces 12 clients voulaient au total     │
  │                │                         │ 18 boîtes de Doliprane.               │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Nombre de clients distincts ayant     │
  │ Nb clients     │ sum(nb_clients_         │ subi une rupture pour ce produit.     │
  │ impactés       │     impactes)           │ 12 clients sont repartis sans leur    │
  │                │                         │ Doliprane ce jour-là.                 │
  ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
  │                │                         │ Nombre de factures (transactions)     │
  │ Nb factures    │ count(distinct          │ concernées par des manquants.         │
  │ impactées      │     FAC_ID)             │ Sur les 12 clients, 10 factures       │
  │                │                         │ distinctes sont concernées.           │
  └────────────────┴─────────────────────────┴───────────────────────────────────────┘

**Différence avec fact_stock_mouvement** : `fact_stock_mouvement` enregistre les niveaux de stock (on sait **quand** le stock est à zéro). `fact_ruptures` enregistre la **demande non servie** (on sait combien de clients et de boîtes ont été impactés par la rupture).


### 1.6 fact_tresorerie — Trésorerie journalière

Table au grain journalier par pharmacie. Chaque ligne contient le résumé financier de la journée : encaissements par mode de paiement, marges par segment et TVA par taux. Source : table `HISTORY`.

  ┌────────────────────────┬─────────────────────────┬───────────────────────────────────────────────────┐
  │ KPI                    │ Formule                 │ Description                                       │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ CA total jour          │ somme des encaissements │ Total encaissé tous modes de paiement confondus   │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Montant espèces        │ EspeceEUR               │ Encaissements en espèces                          │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Montant CB             │ CB                      │ Encaissements par carte bancaire                  │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Montant mutuelle       │ Mutuelle                │ Montants pris en charge par les mutuelles         │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Montant centre         │ Centre                  │ Montants pris en charge par la sécurité sociale   │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Marge remboursable     │ Marge_Rembt             │ Marge sur les produits remboursés                 │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ Marge non remboursable │ Marge_NRembt            │ Marge sur les produits libres (parapharmacie)     │
  ├────────────────────────┼─────────────────────────┼───────────────────────────────────────────────────┤
  │ TVA par taux           │ TVA_1 à TVA_5           │ Montants de TVA collectée par taux (2.1%, 5.5%…)  │
  └────────────────────────┴─────────────────────────┴───────────────────────────────────────────────────┘

*Exemple : le 15 janvier, la pharmacie Dupont a encaissé 4 500 EUR : 800 EUR en espèces, 1 200 EUR en CB, 2 000 EUR en tiers-payant (mutuelle + centre) et 500 EUR en chèques. La marge du jour est de 1 200 EUR dont 800 EUR sur produits remboursés et 400 EUR sur produits libres.*


### 1.7 fact_stock_valorisation — Stock valorisé quotidien

Table au grain journalier par pharmacie et produit. Chaque ligne contient la quantité en stock, les 4 prix du jour et la valorisation calculée. Source : table `STOCKHISTORY` (137M rows).

  ┌──────────────────┬──────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI              │ Formule                      │ Description                                  │
  ├──────────────────┼──────────────────────────────┼──────────────────────────────────────────────┤
  │ Quantité stock   │ STH_STOCK                    │ Nombre d'unités en stock ce jour             │
  ├──────────────────┼──────────────────────────────┼──────────────────────────────────────────────┤
  │ Valeur stock PA  │ quantite × prix_achat_net    │ Valeur du stock au prix d'achat              │
  ├──────────────────┼──────────────────────────────┼──────────────────────────────────────────────┤
  │ Valeur stock PV  │ quantite × prix_public       │ Valeur du stock au prix de vente             │
  ├──────────────────┼──────────────────────────────┼──────────────────────────────────────────────┤
  │ Marge latente    │ valeur PV - valeur PA        │ Marge potentielle si tout le stock est vendu │
  └──────────────────┴──────────────────────────────┴──────────────────────────────────────────────┘

*Exemple : le 15 janvier, la pharmacie a 120 boîtes de Doliprane en stock. Prix achat net = 1.65 EUR, prix public = 3.10 EUR. Valeur stock PA = 198 EUR, valeur stock PV = 372 EUR, marge latente = 174 EUR.*

**Différence avec fact_prix_journalier** : `fact_prix_journalier` contient les prix sans les quantités en stock (source : DAYBYDAY). `fact_stock_valorisation` contient les prix **et** les quantités, permettant de valoriser le stock (source : STOCKHISTORY).


### 1.8 fact_operateur — Ventes par opérateur

Table au grain horaire par pharmacie et opérateur. Chaque ligne contient les ventes agrégées d'un opérateur pour une heure donnée. Source : table `MEDIPRIX_FACTURES` (249M rows) — seule table contenant l'identité du vendeur et l'heure de vente.

  ┌───────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────┐
  │ KPI                   │ Formule                              │ Description                              │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ CA TTC                │ sum(FAC_PVTTC)                       │ CA TTC par opérateur et heure            │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ CA HT                 │ sum(FAC_PVHT)                        │ Chiffre d'affaires HT                    │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Coût achat HT         │ sum(FAC_PAHT)                        │ Coût d'achat des produits vendus         │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Nb lignes             │ count(*)                             │ Nombre de lignes de vente                │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Nb lignes rembours.   │ comptage lignes avec code rembourst  │ Volume de ventes prescrites vs libres    │
  └───────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────┘

*Exemple : l'opérateur MARTIN a vendu 45 lignes entre 9h et 10h le 15 janvier, pour un CA TTC de 380 EUR. Sur ces 45 lignes, 30 sont des produits remboursables.*


---

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


### 2.2 mart_kpi_stock — Rotation et rupture stock mensuelles

**Croisement** : `fact_stock_mouvement` x `fact_ventes`, agrégés au mois.

**Logique** : on calcule le stock moyen du mois à partir des mouvements, puis on le rapproche des quantités vendues pour mesurer la vitesse d'écoulement du stock.

**Grain** : pharmacie, produit, mois.

  ┌───────────────────────┬──────────────────────────────────────────────┐
  │ KPI                   │ Formule                                      │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Stock moyen           │ avg(stock_apres) sur le mois                 │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Stock min             │ min(stock_apres)                             │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Stock max             │ max(stock_apres)                             │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Nb jours rupture      │ Nombre de jours où stock_apres = 0           │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Taux de rupture stock │ nb_jours_rupture / nb_jours_mouvement        │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ Rotation de stock     │ quantite_vendue / stock_moyen                │
  └───────────────────────┴──────────────────────────────────────────────┘

**Explications et exemples :**

- **Stock moyen** : niveau de stock moyen constaté dans le mois.
  *Exemple : en janvier, stocks de 120, 80, 150 sur 3 relevés, stock moyen = 116 boîtes.*

- **Stock min / max** : stock le plus bas et le plus haut atteints dans le mois.
  *Exemple : stock le plus bas = 80 boîtes, le plus haut = 150 boîtes.*

- **Nb jours rupture** : nombre de jours où le produit était indisponible (stock à zéro).
  *Exemple : le stock est tombé à 0 pendant 2 jours (le 10 et le 11 janvier).*

- **Taux de rupture stock** : proportion de jours en rupture par rapport aux jours d'activité. C'est une **vue stock** : on mesure combien de temps le produit est absent du rayon, indépendamment du nombre de clients impactés (source : MODSTOCK).
  *Exemple : 2 jours de rupture / 20 jours de mouvement = 10% de taux de rupture stock.*

- **Rotation de stock** : nombre de fois que le stock "tourne" dans le mois. Plus c'est élevé, plus le produit se vend vite. Une rotation faible indique un sur-stockage.
  *Exemple : 500 boîtes vendues / 116 en stock moyen = 4.3 rotations.*

---

### 2.3 mart_kpi_ecoulement — Taux d'écoulement mensuel

**Croisement** : `fact_commandes` x `fact_ventes`, agrégés au mois.

**Logique** : on compare ce que la pharmacie a commandé à ses fournisseurs avec ce qu'elle a effectivement vendu, pour mesurer l'adéquation approvisionnement/demande.

**Grain** : pharmacie, produit, mois.

  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ KPI                  │ Formule                                      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Quantité commandée   │ sum(quantite_commandee)                      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Montant commandé     │ sum(montant_pahtnet)                         │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Nb commandes         │ count(distinct commande_id)                  │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Quantité vendue      │ sum(quantite_vendue)                         │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ CA HT                │ sum(ca_ht)                                   │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Taux d'écoulement    │ quantite_vendue / quantite_commandee         │
  └──────────────────────┴──────────────────────────────────────────────┘

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

### 2.4 mart_kpi_ruptures — Impact des ruptures et CA perdu

**Croisement** : `fact_ruptures` x `fact_ventes` x `fact_prix_journalier`, agrégés au mois.

**Logique** : on prend les volumes de demande non servie (lignes, boîtes, clients), on les croise avec les ventes réelles pour calculer un taux de rupture côté demande, et on utilise les prix moyens du mois pour estimer le chiffre d'affaires et la marge perdus.

**Grain** : pharmacie, produit, mois.

  ┌─────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │ KPI                     │ Formule                                                          │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Nb lignes manquantes    │ sum(nb_lignes_manquantes) sur le mois                            │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Nb boîtes manquantes    │ sum(nb_boites_manquantes) sur le mois                            │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Nb clients impactés     │ sum(nb_clients_impactes) sur le mois                             │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Nb factures impactées   │ sum(nb_factures_impactees) sur le mois                           │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Nb jours rupture        │ count(distinct date_rupture) dans le mois                        │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Taux de rupture demande │ nb_lignes_manquantes / (nb_lignes_vendues + nb_lignes_manquantes)│
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ CA estimé perdu         │ nb_boites_manquantes × prix_public_moyen                         │
  ├─────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Marge estimée perdue    │ nb_boites_manquantes × (prix_public_moyen - prix_achat_net_moyen)│
  └─────────────────────────┴──────────────────────────────────────────────────────────────────┘

**Explications et exemples :**

- **Nb boîtes manquantes** : total des unités demandées par les clients mais non disponibles dans le mois.
  *Exemple : en janvier, 45 boîtes de Doliprane ont été demandées sans pouvoir être délivrées.*

- **Nb clients impactés** : nombre de clients qui sont repartis sans leur produit.
  *Exemple : 32 clients n'ont pas pu acheter leur Doliprane en janvier.*

- **Nb jours rupture** : nombre de jours distincts où au moins un client a subi une rupture.
  *Exemple : les ruptures sont survenues sur 5 jours différents dans le mois.*

- **Taux de rupture demande** : proportion des lignes de vente non satisfaites par rapport au total (ventes réalisées + manquants). C'est une **vue demande client** : on mesure l'impact réel sur les clients, indépendamment du niveau de stock (source : MANQHISTORY).
  *Exemple : 45 lignes manquantes / (320 lignes vendues + 45 manquantes) = 12.3% de taux de rupture demande.*

- **CA estimé perdu** : valorisation des boîtes manquantes au prix public moyen du mois. Permet de chiffrer le manque à gagner en chiffre d'affaires.
  *Exemple : 45 boîtes × 3.10 EUR prix public moyen = 139.50 EUR de CA perdu.*

- **Marge estimée perdue** : valorisation des boîtes manquantes à la marge unitaire moyenne du mois. Permet de chiffrer l'impact sur le résultat.
  *Exemple : 45 boîtes × (3.10 - 1.65) EUR = 65.25 EUR de marge perdue.*

**Différence avec mart_kpi_stock.taux_rupture_stock** :

  ┌────────────────┬──────────────────────────────────────┬──────────────────────────────────────────┐
  │                │ mart_kpi_stock                       │ mart_kpi_ruptures                        │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Colonne        │ taux_rupture_stock                   │ taux_rupture_demande                     │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Source         │ MODSTOCK (mouvements de stock)       │ MANQHISTORY (demandes non servies)       │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Mesure         │ % jours à stock zéro                 │ % lignes de vente non satisfaites        │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Question       │ "Combien de temps en rupture ?"      │ "Combien de clients a-t-on perdus ?"     │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
  │ Chiffrage CA   │ Non                                  │ Oui (via prix moyen)                     │
  └────────────────┴──────────────────────────────────────┴──────────────────────────────────────────┘

Les deux indicateurs sont complémentaires : un produit peut avoir le stock à zéro un dimanche sans impact client (`taux_rupture_stock` élevé, `taux_rupture_demande` nul), ou inversement avoir du stock mais des lignes manquantes pour un autre motif (produit bloqué, réservé).

---

### 2.5 mart_kpi_tresorerie — Trésorerie mensuelle

**Source** : `fact_tresorerie`, agrégée au mois.

**Logique** : on additionne les encaissements journaliers par mode de paiement, on calcule les pourcentages de répartition et le panier moyen.

**Grain** : pharmacie, mois.

  ┌──────────────────────┬────────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                  │ Formule                                │ Description                                  │
  ├──────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Panier moyen         │ CA total / nb factures                 │ Valeur moyenne d'un passage en caisse        │
  ├──────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % espèces            │ montant espèces / CA total             │ Part des paiements en espèces                │
  ├──────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % CB                 │ montant CB / CA total                  │ Part des paiements par carte                 │
  ├──────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % tiers-payant       │ (mutuelle + centre + subrog.) / CA tot │ Part prise en charge par les organismes      │
  ├──────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % marge rembours.    │ marge remboursable / marge totale      │ Part marge provenant des produits remboursés │
  └──────────────────────┴────────────────────────────────────────┴──────────────────────────────────────────────┘

**Explications et exemples :**

- **Panier moyen** : valeur moyenne d'un passage en caisse. Permet de mesurer le montant dépensé par client.
  *Exemple : 45 000 EUR de CA / 1 500 factures = 30 EUR de panier moyen.*

- **% tiers-payant** : part du CA prise en charge par la sécurité sociale et les mutuelles. Un taux élevé indique une dépendance aux remboursements.
  *Exemple : 28 000 EUR de tiers-payant / 45 000 EUR de CA total = 62% de tiers-payant.*

- **% marge remboursable** : répartition de la marge entre produits remboursés et produits libres (parapharmacie, OTC). Permet de piloter le mix de rentabilité.
  *Exemple : 8 000 EUR de marge remboursable / 12 000 EUR de marge totale = 67%. La pharmacie réalise un tiers de sa marge sur le libre.*


### 2.6 mart_kpi_stock_valorisation — Valorisation et couverture stock

**Croisement** : `fact_stock_valorisation` x `fact_ventes`, agrégés au mois.

**Logique** : on calcule la valeur du stock en fin de mois, la couverture en jours (combien de temps le stock actuel permet de tenir) et on détecte les anomalies (stock dormant, inflation fournisseur).

**Grain** : pharmacie, produit, mois.

  ┌──────────────────────────┬──────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ KPI                      │ Formule                                  │ Description                                      │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Valeur stock PA fin mois │ stock_fin_mois × prix_achat_net          │ Valeur du stock immobilisé (BFR)                 │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Valeur stock PV fin mois │ stock_fin_mois × prix_public             │ Valeur de revente potentielle                    │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Marge latente moyenne    │ avg(valeur PV - valeur PA)               │ Marge potentielle moyenne en rayon               │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Couverture stock (jours) │ stock_fin_mois × 30 / quantite_vendue    │ Nb jours de vente couverts par le stock actuel   │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Variation prix achat     │ (prix fin - prix debut) / prix debut     │ Variation du prix d'achat net dans le mois       │
  ├──────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Stock dormant            │ true si stock > 0 et 0 ventes            │ Produits immobilisant du capital sans rotation   │
  └──────────────────────────┴──────────────────────────────────────────┴──────────────────────────────────────────────────┘

**Explications et exemples :**

- **Couverture de stock** : nombre de jours de vente couverts par le stock actuel. Trop élevé = sur-stockage, trop faible = risque de rupture.
  *Exemple : 120 boîtes en stock, 500 vendues dans le mois. Couverture = 120 × 30 / 500 = 7.2 jours. Le stock ne couvre même pas une semaine de ventes.*

- **Variation prix achat** : détection d'inflation fournisseur. Une hausse significative sur un mois doit déclencher une alerte.
  *Exemple : prix achat net début janvier = 1.65 EUR, fin janvier = 1.72 EUR. Variation = +4.2%.*

- **Stock dormant** : produits ayant du stock mais aucune vente dans le mois. Capital immobilisé inutilement.
  *Exemple : 50 boîtes d'un produit à 8 EUR = 400 EUR de stock dormant. Si c'est chronique, envisager un déstockage.*


### 2.7 mart_kpi_qualite_donnees — Monitoring pipeline

**Sources** : `stg_log` (dernière synchronisation) + `stg_pharmacies_erreur` (erreurs de sync).

**Logique** : on évalue la fraîcheur des données par pharmacie et on résume les erreurs de synchronisation.

**Grain** : pharmacie (snapshot, non temporel).

  ┌────────────────────┬────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                │ Formule                        │ Description                                  │
  ├────────────────────┼────────────────────────────────┼──────────────────────────────────────────────┤
  │ Heures depuis sync │ current_timestamp - DATE_SYNC  │ Fraîcheur des données par pharmacie          │
  ├────────────────────┼────────────────────────────────┼──────────────────────────────────────────────┤
  │ Statut fraîcheur   │ OK / ALERTE / CRITIQUE         │ OK ≤ 24h, ALERTE 24-48h, CRITIQUE > 48h      │
  ├────────────────────┼────────────────────────────────┼──────────────────────────────────────────────┤
  │ Taux pharmacies OK │ nb OK / nb total               │ Part des pharmacies avec données fraîches    │
  ├────────────────────┼────────────────────────────────┼──────────────────────────────────────────────┤
  │ Nb erreurs total   │ count(*)                       │ Nombre total d'erreurs de synchronisation    │
  └────────────────────┴────────────────────────────────┴──────────────────────────────────────────────┘

**Explications et exemples :**

- **Statut fraîcheur** : permet de détecter les pharmacies dont les données ne remontent plus.
  *Exemple : 250 pharmacies OK, 12 en ALERTE (pas de sync depuis 36h), 6 CRITIQUE (> 48h). Les 6 critiques nécessitent une intervention.*

- **Taux pharmacies OK** : indicateur global de santé du pipeline.
  *Exemple : 250 / 268 = 93.3%. Objectif > 95%.*


### 2.8 mart_kpi_operateur — Performance opérateur

**Source** : `fact_operateur`, agrégée au mois.

**Logique** : on mesure la performance de chaque vendeur (opérateur) : volume de ventes, panier moyen, marge générée, profil de vente (prescrit vs libre), et heure de pic d'activité.

**Grain** : pharmacie, opérateur, mois.

  ┌────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                    │ Formule                              │ Description                                  │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA TTC                 │ sum(ca_ttc)                          │ CA total de l'opérateur                      │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Panier moyen           │ CA TTC / nb lignes                   │ Montant moyen par ligne de vente             │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA moyen par jour      │ CA TTC / nb jours activité           │ Productivité journalière                     │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Taux de marge          │ (CA HT - coût achat) / CA HT         │ Rentabilité des ventes de l'opérateur        │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % lignes rembours.     │ nb lignes rembours. / nb lignes      │ Profil de vente prescrit vs libre            │
  ├────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Heure pic CA           │ heure avec le plus de CA TTC         │ Créneau de plus forte activité               │
  └────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Explications et exemples :**

- **Panier moyen par opérateur** : compare la capacité de conseil et de vente additionnelle entre vendeurs.
  *Exemple : opérateur MARTIN a un panier moyen de 35 EUR vs DURAND à 22 EUR. MARTIN réalise davantage de ventes complémentaires.*

- **% lignes remboursables** : profil de vente. Un taux élevé indique un opérateur principalement sur le comptoir prescription. Un taux faible indique un profil parapharmacie/conseil.
  *Exemple : MARTIN 72% remboursable (profil prescription), DURAND 45% (profil conseil/libre).*

- **Heure pic CA** : permet de planifier les équipes aux heures de forte affluence.
  *Exemple : MARTIN réalise le plus de CA entre 10h et 11h. DURAND entre 14h et 15h.*


### 2.9 mart_kpi_abc — Classification Pareto

**Source** : `fact_ventes`, agrégée au mois.

**Logique** : on classe les produits par CA décroissant au sein de chaque pharmacie, puis on calcule le pourcentage cumulé pour attribuer une classe ABC (loi de Pareto : 20% des produits = 80% du CA).

**Grain** : pharmacie, produit, mois.

  ┌────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI            │ Formule                              │ Description                                  │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Rang           │ row_number() order by CA desc        │ Position du produit dans le classement       │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % CA           │ CA produit / CA total pharmacie      │ Poids du produit dans le CA                  │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % CA cumulé    │ somme cumulée du % CA                │ Courbe de Pareto                             │
  ├────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Classe ABC     │ A si ≤ 80%, B si ≤ 95%, C sinon      │ Classification Pareto                        │
  └────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Explications et exemples :**

- **Classe A** (top 80% du CA) : produits stratégiques, ne jamais être en rupture. Typiquement 15-20% des références.
  *Exemple : 150 produits sur 800 génèrent 80% du CA. Doliprane, Efferalgan, Dafalgan sont en classe A.*

- **Classe B** (80-95% du CA) : produits importants mais moins critiques. Environ 30% des références.
  *Exemple : 250 produits supplémentaires couvrent les 15% suivants du CA.*

- **Classe C** (> 95% du CA) : produits à faible rotation, candidats au déstockage. Environ 50% des références pour seulement 5% du CA.
  *Exemple : 400 produits ne génèrent que 5% du CA. Certains pourraient être retirés du catalogue.*

**Utilisation croisée** : la classification ABC peut être croisée avec `mart_kpi_stock` et `mart_kpi_ruptures` pour prioriser les actions :
- Un produit classe A en rupture = urgence absolue (fort impact CA)
- Un produit classe C avec stock dormant = candidat au déstockage


### 2.10 mart_kpi_ca_evolution — Évolution CA vs A-1

**Source** : `fact_ventes`, agrégée au mois avec comparaison année précédente.

**Logique** : on calcule le CA mensuel, le CA cumulé année (YTD) et le CA sur 12 mois glissants, puis on compare à la même période de l'année précédente.

**Grain** : pharmacie, mois.

  ┌──────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                  │ Formule                              │ Description                                  │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT                │ sum(ca_ht)                           │ CA HT du mois                                │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT A-1            │ CA HT du même mois année précédente  │ Base de comparaison                          │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Evolution vs A-1     │ (CA - CA_A1) / CA_A1                 │ Taux de croissance mensuel                   │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT YTD            │ Cumul depuis janvier                 │ CA cumulé année en cours                     │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Evolution YTD vs A-1 │ (YTD - YTD_A1) / YTD_A1              │ Croissance année en cours                    │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT 12DM           │ Somme des 12 derniers mois           │ CA glissant (lisse saisonnalité)             │
  ├──────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Evolution 12DM       │ (12DM - 12DM_A1) / 12DM_A1           │ Tendance de fond                             │
  └──────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Utilités :**
- Mesurer la **croissance annuelle** de l'activité
- Détecter une **baisse de fréquentation** ou de panier
- Comparer aux **objectifs budgétaires**
- Identifier les **tendances saisonnières** (via 12DM)


### 2.11 mart_kpi_generique — Génériques et Parts de Marché Labo

**Croisement** : `fact_ventes` x `dim_produit` x `dim_fournisseur` x `fact_prix_journalier`.

**Logique** : on enrichit les ventes avec la classification générique/univers du produit, le laboratoire, et on calcule la marge et les parts de marché.

**Grain** : pharmacie, laboratoire, univers, is_generique, mois.

  ┌───────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                       │ Formule                              │ Description                                  │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT                     │ sum(ca_ht)                           │ CA par labo/univers/générique                │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Marge brute               │ CA HT - coût achat                   │ Marge en euros                               │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Taux de marge             │ marge_brute / ca_ht                  │ Rentabilité du segment                       │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ PDM labo                  │ CA labo / CA total pharmacie         │ Part de marché du laboratoire                │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Taux générique            │ CA générique / CA total              │ Part des génériques dans le CA               │
  ├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Evolution vs A-1          │ (CA - CA_A1) / CA_A1                 │ Croissance par labo/générique                │
  └───────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Utilités :**
- Suivre la **politique de substitution générique** (objectif CPAM > 80%)
- Identifier les **laboratoires stratégiques** (gros CA)
- Négocier les **conditions commerciales** avec les labos
- Comparer **marge générique vs princeps**


### 2.12 mart_kpi_remise_labo — Remise Pondérée par Laboratoire

**Croisement** : `fact_commandes` x `dim_fournisseur`.

**Logique** : on agrège les commandes par laboratoire et on calcule la remise moyenne pondérée (par quantité ou par montant) pour évaluer les conditions fournisseurs.

**Grain** : pharmacie, laboratoire, mois.

  ┌───────────────────────────┬────────────────────────────────────────────┬────────────────────────────────────────────┐
  │ KPI                       │ Formule                                    │ Description                                │
  ├───────────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Remise moyenne simple     │ avg(remise)                                │ Moyenne arithmétique                       │
  ├───────────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Remise pondérée quantité  │ sum(remise × qte) / sum(qte)               │ Pondérée par volumes commandés             │
  ├───────────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Remise pondérée montant   │ sum(remise × montant) / sum(montant)       │ Pondérée par valeur (KPI principal)        │
  ├───────────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ PDM achats labo           │ montant labo / montant total               │ Part du labo dans les achats               │
  ├───────────────────────────┼────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Evolution remise vs A-1   │ (remise - remise_A1) / remise_A1           │ Évolution des conditions                   │
  └───────────────────────────┴────────────────────────────────────────────┴────────────────────────────────────────────┘

**Utilités :**
- Évaluer la **qualité des accords fournisseurs**
- Comparer les **conditions** entre laboratoires
- Négocier de **meilleures remises**
- Identifier les labos à **fort potentiel** de négociation


### 2.13 mart_kpi_univers — KPIs par Univers (Dashboard)

**Source** : `mart_kpi_generique`, agrégé par univers.

**Logique** : on pré-agrège les KPIs par univers (RX, OTC, PARA, HORS_REMB) pour un affichage direct sur dashboard sans filtre.

**Grain** : pharmacie, univers, mois.

  ┌───────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                   │ Formule                              │ Description                                  │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT                 │ sum(ca_ht) par univers               │ CA de l'univers                              │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Marge brute           │ sum(marge_brute) par univers         │ Marge de l'univers                           │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Taux de marge         │ marge / ca_ht                        │ Rentabilité de l'univers                     │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % CA univers          │ CA univers / CA total pharmacie      │ Part de l'univers dans le CA                 │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % Marge univers       │ marge univers / marge totale         │ Contribution à la rentabilité                │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Evolution vs A-1      │ (CA - CA_A1) / CA_A1                 │ Croissance de l'univers                      │
  └───────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Utilités :**
- Identifier les **univers les plus rentables**
- Orienter le **mix produit** vers les segments à forte marge
- Adapter la **stratégie commerciale** par segment
- Justifier les **investissements** merchandising


### 2.14 mart_kpi_dormant — Produits Sans Vente

**Croisement** : `dim_produit` x `fact_ventes` (cross join avec filtre date dernière vente).

**Logique** : on identifie les produits en stock sans vente depuis 3, 6 ou 12 mois, et on valorise le capital immobilisé.

**Grain** : pharmacie, produit.

  ┌───────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                   │ Formule                              │ Description                                  │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Statut dormant        │ ACTIF, DORMANT_3M, 6M, 12M           │ Classification par ancienneté                │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Jours sans vente      │ current_date - dernière_vente        │ Ancienneté de la dernière vente              │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ is_dormant_6m         │ true si > 180 jours sans vente       │ Flag dormant 6 mois                          │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ is_dormant_12m        │ true si > 365 jours sans vente       │ Flag dormant 12 mois                         │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Valeur stock PA       │ stock × prix_achat                   │ Capital immobilisé                           │
  ├───────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Marge latente bloquée │ stock × (prix_vente - prix_achat)    │ Marge potentielle bloquée                    │
  └───────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Utilités :**
- Identifier le **stock dormant** à risque péremption
- Prioriser les **retours fournisseurs**
- Calculer la **dépréciation comptable**
- Améliorer les **processus d'achat** (objectif < 5%)


### 2.15 mart_kpi_synthese_pharmacie — Vue Dashboard Consolidée

**Croisement** : `mart_kpi_ca_evolution` x `mart_kpi_stock_valorisation` x `mart_kpi_generique` x `mart_kpi_dormant`.

**Logique** : on agrège tous les KPIs clés au niveau pharmacie/mois pour un affichage direct sur dashboard, sans aucun calcul supplémentaire côté application.

**Grain** : pharmacie, mois.

  ┌────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ KPI                        │ Formule                              │ Description                                  │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA HT + evolution          │ Directement depuis ca_evolution      │ CA et croissance vs A-1                      │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Marge brute + taux         │ Agrégé depuis generique              │ Rentabilité globale                          │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Valeur stock               │ sum(valeur_stock_pa)                 │ Capital immobilisé                           │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ **Ratio stock/CA annuel**  │ valeur_stock / ca_ht_ytd × 100       │ KPI clé (cible 8-15%)                        │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ CA générique + taux        │ Agrégé WHERE is_generique            │ Performance substitution                     │
  ├────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ % dormants 6m / 12m        │ nb_dormants / nb_produits            │ Santé du stock (cible < 5%)                  │
  └────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────┘

**Utilités :**
- **Vue exécutive** : tous les KPIs principaux en une seule requête
- **Dashboard temps réel** : aucun calcul côté application
- **Benchmark** : comparaison entre pharmacies du groupement
- **Alertes** : détection automatique des écarts aux cibles

---

## 3. Axes d'analyse (dimensions)

Tous les KPIs ci-dessus peuvent être filtrés et ventilés selon les axes suivants :

  ┌──────────────────┬────────────────────────────────────────────────────────────────┐
  │ Dimension        │ Colonnes disponibles                                           │
  ├──────────────────┼────────────────────────────────────────────────────────────────┤
  │ dim_pharmacie    │ PHA_NOM, external_city, postal_code, PHA_GERS                  │
  ├──────────────────┼────────────────────────────────────────────────────────────────┤
  │ dim_produit      │ PRD_NOM, EAN13, PRD_CODEREMBT, PRD_CODEACTE, LPP_CODE, PRD_TVA │
  ├──────────────────┼────────────────────────────────────────────────────────────────┤
  │ dim_fournisseur  │ FOU_NOM, FOU_VILLE, FOU_TYPE, FOU_REPARTITEUR                  │
  ├──────────────────┼────────────────────────────────────────────────────────────────┤
  │ Temporel         │ date_vente, date_commande, date_prix, date_mouvement, mois     │
  └──────────────────┴────────────────────────────────────────────────────────────────┘

**Exemples d'analyses possibles :**

- CA par pharmacie, par ville, par zone géographique
- Marge par famille de produit, analyse par code remboursement
- Performance par fournisseur, comparaison entre répartiteurs
- Évolution mensuelle, saisonnalité, tendances

---

## 4. Classification des KPIs par catégorie commerciale

Cette section classe les KPIs selon les catégories standard du commerce et de la distribution.

### 4.1 Sell-in (achats fournisseurs → pharmacie)

KPIs mesurant les flux d'approvisionnement auprès des grossistes et laboratoires.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Montant commandé (PAHT net)     │ fact_commandes          │ Valeur des achats fournisseurs              │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Quantités commandées            │ fact_commandes          │ Volume des achats                           │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Remise fournisseur moyenne      │ fact_commandes          │ Conditions obtenues                         │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Nb commandes                    │ fact_commandes          │ Fréquence des réapprovisionnements          │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Remise pondérée quantité/montant│ mart_kpi_remise_labo    │ Remise réelle tenant compte des volumes     │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ PDM achats labo                 │ mart_kpi_remise_labo    │ Répartition des achats par laboratoire      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Evolution remise vs A-1         │ mart_kpi_remise_labo    │ Tendance des conditions fournisseurs        │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Délai d'approvisionnement       │ NON DISPO               │ Requiert table RECEPTIONS                   │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Taux de service fournisseur     │ NON DISPO               │ Requiert table RECEPTIONS                   │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘


### 4.2 Sell-out (pharmacie → consommateur final)

KPIs mesurant les ventes au comptoir, l'activité commerciale B2C.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA HT / CA TTC                  │ fact_ventes             │ Chiffre d'affaires                          │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Quantités vendues               │ fact_ventes             │ Volume de ventes                            │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Nb lignes de vente              │ fact_ventes             │ Nombre de transactions                      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Panier moyen                    │ fact_ventes             │ Montant moyen par passage en caisse         │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Marge brute / Taux de marge     │ mart_kpi_marge          │ Rentabilité des ventes                      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA + Evolution vs A-1/YTD/12DM  │ mart_kpi_ca_evolution   │ Croissance de l'activité                    │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA par labo / PDM labo          │ mart_kpi_generique      │ Répartition par laboratoire                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA par univers (RX/OTC/PARA)    │ mart_kpi_univers        │ Répartition par segment                     │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA opérateur / Panier opérateur │ mart_kpi_operateur      │ Performance par vendeur                     │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA par catégorie                │ NON DISPO               │ Requiert référentiel catégories             │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Unités vendues par catégorie    │ NON DISPO               │ Requiert référentiel catégories             │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Marge par catégorie             │ NON DISPO               │ Requiert référentiel catégories             │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Evolution par catégorie         │ NON DISPO               │ Requiert référentiel catégories             │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘


### 4.3 Sell-through (taux d'écoulement / rotation)

KPIs mesurant la vitesse à laquelle les produits achetés sont revendus.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Taux d'écoulement               │ mart_kpi_ecoulement     │ % des achats revendus dans le mois          │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Rotation de stock               │ mart_kpi_stock          │ Nb de fois que le stock tourne/mois         │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Couverture stock (jours)        │ mart_kpi_stock_valor.   │ Nb jours de vente couverts                  │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Stock dormant                   │ mart_kpi_dormant        │ Produits sans vente depuis 3/6/12 mois      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Ratio stock/CA annuel           │ mart_kpi_synthese_pha.  │ Poids du stock vs activité (cible 8-15%)    │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘


### 4.4 Upsell / Upselling (montée en gamme)

KPIs mesurant la capacité à vendre des produits de gamme supérieure.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ (aucun KPI explicite)           │ —                       │ Nécessite analyse comparative des gammes    │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*Exemple d'upsell en pharmacie : proposer Nurofen 400mg au lieu de Nurofen 200mg, ou une crème premium au lieu d'une crème standard.*


### 4.5 Cross-sell / Cross-selling (ventes additionnelles)

KPIs mesurant la capacité à vendre des produits complémentaires.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Panier moyen (indirect)         │ fact_ventes             │ Un panier élevé suggère du cross-sell       │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Nb lignes par facture (indirect)│ fact_ventes             │ Plus de lignes = plus de produits associés  │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*Exemple de cross-sell en pharmacie : proposer un spray nasal avec un sirop contre la toux, ou une brosse à dents avec un dentifrice.*


### 4.6 Downsell / Down-selling (substitution vers moins cher)

KPIs mesurant la substitution vers des produits moins chers (notamment génériques).

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ Taux générique                  │ mart_kpi_generique      │ % CA générique vs princeps                  │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ CA générique vs princeps        │ mart_kpi_generique      │ Comparaison des ventes par type             │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*En pharmacie, le downsell est souvent encouragé (substitution générique) car il améliore la marge tout en réduisant le coût pour le patient et l'assurance maladie (objectif CPAM > 80%).*


### 4.7 Repeat / Réachat

KPIs mesurant la fidélité et la récurrence des achats clients.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ (aucun KPI)                     │ NON DISPO               │ Requiert suivi client individuel Mediplace  │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*KPIs cibles si données Mediplace disponibles : fréquence de visite, délai moyen entre achats, taux de réachat à 30/60/90 jours.*


### 4.8 Churn (attrition client)

KPIs mesurant la perte de clients.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ (aucun KPI)                     │ NON DISPO               │ Requiert suivi client individuel Mediplace  │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*KPIs cibles si données Mediplace disponibles : taux de churn mensuel, nb clients perdus, CA perdu par churn.*


### 4.9 CLV / LTV (Customer Lifetime Value)

KPIs mesurant la valeur totale d'un client sur sa durée de vie.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ (aucun KPI)                     │ NON DISPO               │ Requiert historique client Mediplace        │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*KPI cible : CLV = panier moyen × fréquence annuelle × durée relation (années). Nécessite identification client.*


### 4.10 Attach rate (taux d'association produits)

KPIs mesurant la fréquence d'achat conjoint de produits.

  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────────────────────────┐
  │ KPI                             │ Source                  │ Description                                 │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────────────────────────┤
  │ (aucun KPI)                     │ NON DISPO               │ Requiert analyse de panier (market basket)  │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────────────────────────┘

*KPI cible : % de paniers contenant le produit A qui contiennent aussi le produit B. Exemple : 65% des clients achetant un sirop achètent aussi des pastilles.*


### 4.11 Synthèse de couverture

  ┌─────────────────────────┬────────────┬─────────────────────────────────────────────────────────────┐
  │ Catégorie               │ Statut     │ Commentaire                                                 │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Sell-in                 │ COUVERT    │ 7 KPIs disponibles, 2 NON DISPO (réceptions)                │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Sell-out                │ COUVERT    │ 9 KPIs disponibles, 4 NON DISPO (catégories)                │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Sell-through            │ COUVERT    │ 5 KPIs disponibles                                          │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Upsell                  │ NON COUVERT│ Nécessite analyse comparative des gammes produits           │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Cross-sell              │ PARTIEL    │ 2 indicateurs indirects (panier moyen, nb lignes)           │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Downsell                │ COUVERT    │ Via substitution générique                                  │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Repeat / Réachat        │ NON COUVERT│ Requiert données Mediplace (suivi client)                   │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Churn                   │ NON COUVERT│ Requiert données Mediplace (suivi client)                   │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ CLV / LTV               │ NON COUVERT│ Requiert données Mediplace (historique client)              │
  ├─────────────────────────┼────────────┼─────────────────────────────────────────────────────────────┤
  │ Attach rate             │ NON COUVERT│ Requiert analyse de panier (market basket analysis)         │
  └─────────────────────────┴────────────┴─────────────────────────────────────────────────────────────┘

---

## 5. KPIs manquants et plan d'action

Deux KPIs ne sont pas calculables aujourd'hui car les données sources nécessaires n'existent pas dans le pipeline.

### 5.1 Délai d'approvisionnement

**Définition** : temps écoulé entre la date de commande au fournisseur et la date de réception effective de la marchandise à la pharmacie.

**Formule cible** : `delai_moyen = avg(date_reception - date_commande)` en jours.

**Exemple concret** : une commande passée le 5 janvier et reçue le 7 janvier a un délai de 2 jours. Si le fournisseur OCP a un délai moyen de 1.5 jours et Alliance de 2.8 jours, on sait qu'OCP est plus rapide.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la date de commande (`COM_DATE` dans la table `COMMANDES`), mais aucune table source ne contient la date de réception.

### 5.2 Taux de service fournisseur

**Définition** : rapport entre la quantité effectivement livrée par le fournisseur et la quantité commandée.

**Formule cible** : `taux_service = quantite_recue / quantite_commandee`.

**Exemple concret** : on commande 100 boîtes de Doliprane, le fournisseur en livre 95. Le taux de service est de 95%. Un fournisseur en dessous de 90% pose un problème de fiabilité.

**Pourquoi ce n'est pas possible aujourd'hui** : on connaît la quantité commandée (`COM_QUANTITE` dans la table `COMMANDES`), mais aucune table source ne contient la quantité effectivement reçue.

### 5.3 Solution : table source à intégrer

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

  ┌────────────────────────────┬─────────────────────────────────────────────────────┐
  │ KPI                        │ Formule                                             │
  ├────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Délai d'approvisionnement  │ avg(date_reception - date_commande)                 │
  ├────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Taux de service            │ sum(quantite_recue) / sum(quantite_commandee)       │
  ├────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Taux de livraison complète │ count(réceptions complètes) / count(commandes)      │
  └────────────────────────────┴─────────────────────────────────────────────────────┘

**Exemples :**

- OCP livre en moyenne en 1.5 jours
- OCP livre 97% des quantités commandées
- 92% des commandes OCP arrivent complètes


### 5.4 KPIs nécessitant des données externes

Les KPIs suivants ne sont pas disponibles car ils dépendent de sources de données non encore intégrées au pipeline.

#### 5.4.1 Cartes de fidélité créées

**Définition** : nombre de nouvelles cartes de fidélité créées par la pharmacie sur une période donnée.

**Source requise** : API Mediplace ou table MySQL `mediplace.client`

**Structure minimale :**
```
mediplace.client
├── client_id        INT          -- Identifiant client unique
├── pharmacie_id     INT          -- Pharmacie ayant créé la carte
├── date_creation    DATETIME     -- Date de création de la carte
├── type_carte       VARCHAR      -- Type (fidélité, premium, etc.)
└── statut           VARCHAR      -- Actif, inactif, suspendu
```

**KPI cible** : `nb_cartes_creees = count(client_id) WHERE date_creation BETWEEN debut AND fin`

**Utilités :**
- Mesurer l'**acquisition client** de la pharmacie
- Suivre l'efficacité des **campagnes de fidélisation**
- Comparer les **performances commerciales** entre équipes


#### 5.4.2 Montant de challenges Medila

**Définition** : montant total des ventes réalisées dans le cadre de challenges commerciaux Mediplace.

**Source requise** : API Mediplace ou table MySQL `mediplace.challenge_vente`

**Structure minimale :**
```
mediplace.challenge_vente
├── challenge_id     INT          -- Identifiant du challenge
├── pharmacie_id     INT          -- Pharmacie participante
├── operateur_id     INT          -- Opérateur ayant réalisé la vente
├── montant          DECIMAL      -- Montant de la vente challenge
├── date_vente       DATETIME     -- Date de la vente
└── statut           VARCHAR      -- Validé, en attente, annulé
```

**KPI cible** : `montant_challenges = sum(montant) WHERE statut = 'Validé'`

**Utilités :**
- Évaluer la **participation aux opérations commerciales**
- Calculer les **primes et incentives** des équipes
- Mesurer le **ROI des challenges** par rapport à l'investissement marketing


#### 5.4.3 KPIs par catégorie de marché

**Définition** : analyse des ventes par catégorie marketing (Dermo-cosmétique, Hygiène bucco-dentaire, Compléments alimentaires, etc.)

**Source requise** : Référentiel catégories produit (à créer)

**Structure minimale :**
```
ref_categories_produit
├── PRD_ID              INT          -- Identifiant produit (jointure dim_produit)
├── EAN13               VARCHAR(13)  -- Code EAN13 alternatif
├── categorie_niveau1   VARCHAR      -- Macro-catégorie (ex: Médication familiale)
├── categorie_niveau2   VARCHAR      -- Sous-catégorie (ex: Douleur, Fièvre)
└── categorie_marche    VARCHAR      -- Segment marché (ex: OTC Rhume)
```

**KPIs cibles :**

  ┌─────────────────────────────┬─────────────────────────────────────────────────┬───────────────────────────────────────────────┐
  │ KPI                         │ Formule                                         │ Description                                   │
  ├─────────────────────────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ CA par catégorie            │ sum(ca_ht) GROUP BY categorie                   │ Répartition du CA par segment                 │
  ├─────────────────────────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ Unités vendues par catég.   │ sum(quantite) GROUP BY categorie                │ Volume de ventes par segment                  │
  ├─────────────────────────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ Marge par catégorie         │ sum(marge_brute) GROUP BY categorie             │ Rentabilité par segment                       │
  ├─────────────────────────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ Taux de marge par catég.    │ sum(marge) / sum(ca_ht) GROUP BY categorie      │ Rentabilité relative par segment              │
  ├─────────────────────────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────────┤
  │ Evolution par catégorie     │ (CA_N - CA_N1) / CA_N1 GROUP BY categorie       │ Croissance vs année précédente                │
  └─────────────────────────────┴─────────────────────────────────────────────────┴───────────────────────────────────────────────┘

**Exemples concrets :**

*Exemple 1 — Unités vendues par catégorie :*
Une pharmacie vend en janvier :
- Dermo-cosmétique : 1 200 unités (crèmes, soins visage)
- Hygiène bucco-dentaire : 800 unités (dentifrices, brosses)
- Compléments alimentaires : 450 unités (vitamines, magnésium)

→ La catégorie "Dermo-cosmétique" représente 49% des unités vendues. Si le panier moyen est faible (15€), on peut envisager des actions pour augmenter le cross-selling.

*Exemple 2 — Marge par catégorie :*
Sur le même mois :
- Dermo-cosmétique : CA 18 000€, marge 5 400€ (taux 30%)
- Hygiène bucco-dentaire : CA 4 000€, marge 1 200€ (taux 30%)
- Compléments alimentaires : CA 9 000€, marge 3 600€ (taux 40%)

→ Les compléments alimentaires ont le meilleur taux de marge (40%). Développer ce segment permettrait d'améliorer la rentabilité globale.

*Exemple 3 — Evolution par catégorie :*
Comparaison janvier N vs janvier N-1 :
- Dermo-cosmétique : 18 000€ vs 15 000€ → +20%
- Hygiène bucco-dentaire : 4 000€ vs 4 500€ → -11%
- Compléments alimentaires : 9 000€ vs 6 000€ → +50%

→ L'hygiène bucco-dentaire régresse (-11%) alors que les compléments explosent (+50%). Peut-être un changement de fournisseur ou de gamme sur le bucco-dentaire ?

**Utilités :**
- Analyser le **positionnement commercial** de la pharmacie par segment
- Identifier les **catégories sous-exploitées** à développer
- Repérer les **catégories à forte marge** pour orienter le conseil
- Comparer aux **parts de marché nationales** (benchmarks GERS/IMS)
- Piloter le **merchandising** et l'allocation des linéaires
- Mesurer l'impact des **animations commerciales** par catégorie
