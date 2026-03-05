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
