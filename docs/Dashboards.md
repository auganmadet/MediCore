# Dashboards Metabase — Guide utilisateur

Ce document est un mode d'emploi pour créer les dashboards MediCore dans
l'interface web Metabase. Toutes les étapes décrivent les actions manuelles
à effectuer dans le navigateur (`http://localhost:3000`).

> **Séparation des responsabilités** : les cards Metabase font uniquement des `SELECT` sur les tables MARTS pré-calculées par dbt. Les `SUM()`, `AVG()`, `COUNT()` présents dans les équivalents SQL sont des **agrégations d'affichage** (regrouper par mois, par pharmacie, etc.), pas des calculs métier. La logique métier (formules, KPIs) est entièrement dans dbt — voir [`docs/KPIs.md`](KPIs.md) pour les formules détaillées.
>
> **Pourquoi des agrégations dans Metabase et pas dans dbt ?** Les agrégations d'affichage (`SUM`, `AVG`, `COUNT`) sont **dynamiques** — elles s'adaptent aux filtres choisis par l'utilisateur. Par exemple, `SUM(CA_HT)` calcule le total pour une seule pharmacie si l'utilisateur filtre dessus, ou pour toutes les pharmacies sans filtre. Pré-calculer chaque combinaison de filtres dans dbt multiplierait les tables inutilement. Le bon modèle : dbt calcule les KPIs au **grain le plus fin** (par pharmacie, par mois, par produit), et Metabase agrège à la volée selon les filtres de l'utilisateur.

---

## Table des matières

- [1. Entités Metabase](#1-entités-metabase)
  - [La question (card) en détail](#la-question-card-en-détail)
  - [Relations entre entités](#relations-entre-entités)
  - [Grille du dashboard](#grille-du-dashboard)
  - [Stockage et sauvegarde](#stockage-et-sauvegarde)
  - [Filtres cascadés (linked filters)](#filtres-cascadés-linked-filters)
- [2. Structure des collections MediCore](#2-structure-des-collections-medicore)
- [3. Procédure générale de création d'un dashboard](#3-procédure-générale-de-création-dun-dashboard)
- [4. D11 — Produits dormants (exemple détaillé)](#4-d11--produits-dormants-exemple-détaillé)
- [5. Les 15 autres dashboards](#5-les-15-autres-dashboards)
  - [D1 — Vue d'ensemble pharmacie](#d1--vue-densemble-pharmacie)
  - [D2 — Évolution CA](#d2--évolution-ca)
  - [D3 — Trésorerie](#d3--trésorerie)
  - [D4 — Marge détaillée](#d4--marge-détaillée)
  - [D5 — Performance vendeurs](#d5--performance-vendeurs)
  - [D6 — Univers RX/OTC/PARA](#d6--univers-rxotcpara)
  - [D7 — Stock et rotation](#d7--stock-et-rotation)
  - [D8 — Ruptures et CA perdu](#d8--ruptures-et-ca-perdu)
  - [D9 — Écoulement (sell-through)](#d9--écoulement-sell-through)
  - [D10 — Remises fournisseurs](#d10--remises-fournisseurs)
  - [D12 — Classification ABC (Pareto)](#d12--classification-abc-pareto)
  - [D13 — Génériques et labos](#d13--génériques-et-labos)
  - [D14 — Qualité des données](#d14--qualité-des-données)
  - [D15 — Détail transactions (drill-down)](#d15--détail-transactions-drill-down)
  - [D16 — Prix et mouvements stock](#d16--prix-et-mouvements-stock)
  - [Synthèse des filtres par dashboard](#synthèse-des-filtres-par-dashboard)
- [6. Récapitulatif des 16 dashboards](#6-récapitulatif-des-16-dashboards)
- [7. Couverture des 26 tables MARTS](#7-couverture-des-26-tables-marts)
- [8. Conseils pratiques](#8-conseils-pratiques)
- [9. Donner accès aux dashboards à d'autres utilisateurs](#9-donner-accès-aux-dashboards-à-dautres-utilisateurs)
  - [Étape 1 — Créer les groupes par service](#étape-1--créer-les-groupes-par-service)
  - [Étape 2 — Créer les comptes utilisateurs](#étape-2--créer-les-comptes-utilisateurs)
  - [Étape 3 — Configurer les droits sur les collections](#étape-3--configurer-les-droits-sur-les-collections)
  - [Étape 4 — Configurer les droits sur les données](#étape-4--configurer-les-droits-sur-les-données)
  - [Étape 5 — Rendre Metabase accessible sur le réseau](#étape-5--rendre-metabase-accessible-sur-le-réseau)
  - [Étape 6 — Configurer l'envoi d'emails](#étape-6--configurer-lenvoi-demails-optionnel)
  - [Checklist d'ouverture des accès](#récapitulatif--checklist-douverture-des-accès)

---

## 1. Entités Metabase

Metabase organise le contenu en 3 entités :

┌─────────────────┬────────────────────────────────────────────────────────────────────────┐
│ Entité          │ Description                                                            │
├─────────────────┼────────────────────────────────────────────────────────────────────────┤
│ Collection      │ Dossier pour organiser questions et dashboards. Peut contenir des      │
│                 │ sous-collections. Gère les permissions d'accès.                        │
├─────────────────┼────────────────────────────────────────────────────────────────────────┤
│ Question (card) │ L'unité de base de Metabase. Une question = une requête vers           │
│                 │ Snowflake + une visualisation. Tout est une card : un chiffre clé,     │
│                 │ un graphe en barres, une courbe, un camembert ou un tableau.           │
│                 │ Se crée via « + Nouveau > Question ».                                  │
├─────────────────┼────────────────────────────────────────────────────────────────────────┤
│ Dashboard       │ Page regroupant plusieurs questions sur une grille. Supporte des       │
│                 │ filtres globaux et des filtres cascadés (liés entre eux).              │
│                 │ Se crée via « + Nouveau > Dashboard ».                                 │
└─────────────────┴────────────────────────────────────────────────────────────────────────┘

### La question (card) en détail

Une question est composée de deux parties :

**1. La requête** — comment récupérer les données :

┌──────────┬──────────────────────────────────────────────────────────────────────────────┐
│ Mode     │ Description                                                                  │
├──────────┼──────────────────────────────────────────────────────────────────────────────┤
│ MBQL     │ Requête construite via l'éditeur visuel (clic sur table, colonnes, filtres,  │
│          │ regroupements). Metabase génère un JSON interne (pMBQL). Suffisant pour les  │
│          │ requêtes sur une seule table : agrégations, filtres, tri.                    │
├──────────┼──────────────────────────────────────────────────────────────────────────────┤
│ SQL natif│ Requête SQL écrite à la main. Nécessaire dès qu'on a besoin de JOIN entre    │
│          │ plusieurs tables, de sous-requêtes, ou de fonctions Snowflake spécifiques.   │
│          │ Les filtres dashboard utilisent des template tags : `{{paramètre}}` pour     │
│          │ obligatoire, `[[AND colonne = {{paramètre}}]]` pour optionnel.               │
└──────────┴──────────────────────────────────────────────────────────────────────────────┘

**2. La visualisation** (`display`) — comment afficher les données :

┌─────────────────┬─────────────────────────────────┬──────┐
│ display         │ Rendu visuel                    │ Nb   │
├─────────────────┼─────────────────────────────────┼──────┤
│ scalar          │ Nombre unique (chiffre clé)     │ 21   │
├─────────────────┼─────────────────────────────────┼──────┤
│ bar             │ Graphique en barres             │ 30   │
├─────────────────┼─────────────────────────────────┼──────┤
│ line            │ Courbe temporelle               │ 20   │
├─────────────────┼─────────────────────────────────┼──────┤
│ pie             │ Camembert                       │ 9    │
├─────────────────┼─────────────────────────────────┼──────┤
│ table           │ Tableau de données              │ 16   │
├─────────────────┼─────────────────────────────────┼──────┤
│ area            │ Aire empilée                    │ 1    │
└─────────────────┴─────────────────────────────────┴──────┘

> **Vocabulaire** : dans l'UI Metabase, on parle parfois d'« indicateur » pour
> une question affichant un chiffre clé (`scalar`), et de « requête » pour désigner
> le SQL ou MBQL à l'intérieur. Ce sont des usages courants, pas des entités distinctes.
> L'objet technique sous-jacent est toujours une `card`.

### Relations entre entités

```
Collection (dossier)
├── Question MBQL (card, display: bar)
├── Question MBQL (card, display: scalar — « indicateur »)
├── Question SQL natif (card, display: table)
├── Dashboard (page de visualisation)
│     ├── Question 1 (positionnée sur la grille)
│     ├── Question 2
│     └── Question 3
└── Sous-collection
      └── …
```

### Grille du dashboard

La grille Metabase fait **24 colonnes** de large. Quand on place une question
sur un dashboard (mode édition), on la redimensionne par glisser-déposer :

- **Largeur** : de 1 à 24 colonnes (24 = pleine largeur)
- **Hauteur** : en unités de lignes (~60 px chacune)
- **Position** : glisser la question à l'endroit souhaité sur la grille

### Stockage et sauvegarde

Les dashboards et questions sont stockés dans la **base PostgreSQL interne** de
Metabase (conteneur `metabase_db`, volume Docker `metabase_data`). Ce n'est pas
du fichier plat — tout est en base relationnelle.

┌─────────────────────────┬────────────────────────────────────────────────────────┐
│ Méthode                 │ Commande / URL                                         │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Export API (1 dashboard)│ GET /api/dashboard/{id} → JSON complet                 │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Export API (1 question) │ GET /api/card/{id} → JSON complet                      │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Export API (collection) │ GET /api/collection/{id}/items → liste des éléments    │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Dump PostgreSQL complet │ docker exec metabase_db pg_dump -U metabase metabase   │
│                         │ > metabase_backup.sql                                  │
└─────────────────────────┴────────────────────────────────────────────────────────┘

### Filtres cascadés (linked filters)

Les filtres d'un dashboard peuvent être **liés entre eux** : quand on sélectionne
une valeur dans un filtre parent, les filtres dépendants ne proposent que les
valeurs qui existent pour cette sélection. Cela évite les combinaisons impossibles
(ex. pharmacie X + fournisseur Y qui n'a jamais livré cette pharmacie).

Configuration actuelle des filtres cascadés :

┌──────────────────┬─────────────────────────────────────┬──────────────────────────┐
│ Filtre dépendant │ Filtré par (parent)                 │ Dashboards concernés     │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Mois             │ Pharmacie                           │ D1, D3, D5, D6, D7, D8,  │
│                  │                                     │ D9, D10, D12, D13        │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Date             │ Pharmacie                           │ D4, D15, D16             │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Fournisseur      │ Pharmacie + Mois                    │ D10, D13                 │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Fournisseur      │ Pharmacie                           │ D11                      │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Opérateur        │ Pharmacie                           │ D5                       │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Univers          │ Pharmacie + Mois                    │ D13                      │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Univers          │ Pharmacie                           │ D11                      │
├──────────────────┼─────────────────────────────────────┼──────────────────────────┤
│ Statut dormant   │ Pharmacie                           │ D11                      │
└──────────────────┴─────────────────────────────────────┴──────────────────────────┘

Le filtre **Pharmacie** est toujours le filtre racine (aucun parent). L'ordre de
sélection recommandé : Pharmacie → Fournisseur/Opérateur/Univers → Mois/Date.

[↑ Retour au sommaire](#table-des-matières)

---

## 2. Structure des collections MediCore

Avant de créer les dashboards, organiser les collections :

### Étape : créer les collections

1. Cliquer sur **+ Nouveau** > **Collection**
2. Nommer la collection racine : `MediCore BI`
3. Cliquer sur **Créer**
4. Entrer dans `MediCore BI`, puis répéter pour chaque sous-collection :

┌───────────────────────────┬──────────────────────────────┐
│ Collection                │ Dashboards contenus          │
├───────────────────────────┼──────────────────────────────┤
│ Direction Générale        │ D1, D2, D3                   │
├───────────────────────────┼──────────────────────────────┤
│ Ventes & Performance      │ D4, D5, D6                   │
├───────────────────────────┼──────────────────────────────┤
│ Achats & Stock            │ D7, D8, D9, D10, D11         │
├───────────────────────────┼──────────────────────────────┤
│ Qualité & Pilotage        │ D12, D13, D14                │
├───────────────────────────┼──────────────────────────────┤
│ Détail opérationnel       │ D15, D16                     │
└───────────────────────────┴──────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 3. Procédure générale de création d'un dashboard

Cette procédure s'applique à tous les 16 dashboards. Les sections suivantes
détaillent chaque dashboard avec ses questions spécifiques.

### Étape A — Créer le dashboard

1. Naviguer dans la collection cible (ex. `Achats & Stock`)
2. Cliquer sur **+ Nouveau** > **Dashboard**
3. Saisir le nom (ex. `D11 - Produits dormants`)
4. Saisir la description
5. Vérifier que la collection est correcte
6. Cliquer sur **Créer**

### Étape B — Créer les questions et les ajouter au dashboard

Depuis le dashboard en mode édition (crayon en haut à droite) :

1. Cliquer sur **+** (ajouter) > **Question existante** ou **Nouvelle question**
2. Pour une **nouvelle question** :
   - Sélectionner la base de données : `MEDIcore`
   - Sélectionner la table source (ex. `MART_KPI_DORMANT`)
   - Configurer les colonnes, agrégations, filtres et regroupements
   - Choisir le type de visualisation (nombre, barres, camembert, tableau…)
   - Cliquer sur **Sauvegarder** > choisir la collection > **Enregistrer**
3. La question apparaît sur la grille du dashboard
4. **Redimensionner** et **repositionner** par glisser-déposer
5. Répéter pour chaque question du dashboard

### Étape C — Ajouter des filtres au dashboard

1. En mode édition, cliquer sur l'icône **filtre** (entonnoir)
2. Choisir le type de filtre (texte, nombre, date…)
3. Relier le filtre aux colonnes correspondantes de chaque question
4. Cliquer sur **Enregistrer**

[↑ Retour au sommaire](#table-des-matières)

---

## 4. D11 — Produits dormants (exemple détaillé)

### Pourquoi ce dashboard

Un produit dormant = du capital immobilisé qui ne génère aucun revenu. Ce dashboard
déclenche un plan d'action concret : retourner au fournisseur, brader, ou passer en
perte. Le top 20 par valeur priorise les actions à fort impact financier.

**Collection** : Achats & Stock
**Table source** : `MART_KPI_DORMANT` (schéma MARTS)
**Filtres recommandés** : pharmacie, statut dormant, univers, fournisseur

### Colonnes disponibles dans MART_KPI_DORMANT

┌─────────────────────────────┬────────────────┬──────────────────────────────────────┐
│ Colonne                     │ Type           │ Description                          │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ PRODUIT_SK                  │ Texte          │ Clé surrogate produit                │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ PHARMACIE_SK                │ Texte          │ Clé surrogate pharmacie              │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ PHA_ID                      │ Nombre         │ Identifiant pharmacie                │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ PRD_ID                      │ Nombre         │ Identifiant produit                  │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ PRD_NOM                     │ Texte          │ Nom du produit                       │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ FOU_ID                      │ Texte          │ Identifiant fournisseur              │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ FOU_NOM                     │ Texte          │ Nom du fournisseur                   │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ UNIVERS                     │ Texte          │ Univers produit (RX, OTC, PARA)      │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ IS_GENERIQUE                │ Booléen        │ Produit générique oui/non            │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ QUANTITE_STOCK              │ Nombre         │ Quantité en stock                    │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ VALEUR_STOCK_PA             │ Nombre         │ Valeur stock au prix d'achat (€)     │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ VALEUR_STOCK_PV             │ Nombre         │ Valeur stock au prix de vente (€)    │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ DERNIERE_VENTE_PRODUIT      │ Date           │ Dernière vente du produit            │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ DERNIERE_VENTE_EFFECTIVE    │ Date           │ Dernière vente effective             │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ DERNIERE_VENTE              │ Date           │ Dernière vente (toutes sources)      │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ JOURS_SANS_VENTE            │ Nombre         │ Nombre de jours sans vente           │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ STATUT_DORMANT              │ Texte          │ Statut : actif, dormant_3m, 6m, 12m  │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ IS_DORMANT_6M               │ Booléen        │ Dormant depuis 6 mois oui/non        │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ IS_DORMANT_12M              │ Booléen        │ Dormant depuis 12 mois oui/non       │
├─────────────────────────────┼────────────────┼──────────────────────────────────────┤
│ MARGE_LATENTE_BLOQUEE       │ Nombre         │ Marge bloquée par le stock (€)       │
└─────────────────────────────┴────────────────┴──────────────────────────────────────┘

### Création du dashboard

1. Naviguer dans **MediCore BI** > **Achats & Stock**
2. Cliquer sur **+ Nouveau** > **Dashboard**
3. Nom : `D11 - Produits dormants`
4. Description : `Capital immobilisé, dormants par fournisseur et univers`
5. Cliquer sur **Créer**

Le dashboard vide s'ouvre en mode édition.

### Question 1 : Capital immobilisé (dormants 6m) — Indicateur

**Objectif** : afficher la somme de la valeur stock PA des produits dormants 6 mois.

1. Dans le dashboard en mode édition, cliquer sur **+** > **Nouvelle question**
2. Sélectionner la base **MEDIcore** > table **MART_KPI_DORMANT**
3. Cliquer sur **Résumer** (icône sigma Σ)
4. Choisir **Somme de…** > `VALEUR_STOCK_PA`
5. Cliquer sur **Filtrer** > `IS_DORMANT_6M` > sélectionner **true**
6. Cliquer sur **Visualiser** — le résultat s'affiche comme un nombre unique
7. Vérifier que la visualisation est « **Nombre** » (sinon cliquer sur Visualisation > Nombre)
8. Cliquer sur **Enregistrer** > collection `Achats & Stock` > nom : `Capital immobilisé (dormants 6m)`
9. La question apparaît sur le dashboard — la placer en **haut à gauche** (largeur : 8 colonnes)

**Équivalent SQL** :
```sql
SELECT SUM(VALEUR_STOCK_PA)
FROM MARTS.MART_KPI_DORMANT
WHERE IS_DORMANT_6M = true
```

### Question 2 : Nb produits dormants 6m — Indicateur

**Objectif** : compter le nombre de produits dormants depuis 6 mois.

1. Cliquer sur **+** > **Nouvelle question**
2. Sélectionner **MEDIcore** > **MART_KPI_DORMANT**
3. Cliquer sur **Résumer** > **Comptage**
4. Cliquer sur **Filtrer** > `IS_DORMANT_6M` > **true**
5. Cliquer sur **Visualiser** — résultat en nombre unique
6. **Enregistrer** dans `Achats & Stock` sous le nom `Nb produits dormants 6m`
7. Placer à côté de la question 1 (largeur : 8 colonnes, même ligne)

**Équivalent SQL** :
```sql
SELECT COUNT(*)
FROM MARTS.MART_KPI_DORMANT
WHERE IS_DORMANT_6M = true
```

### Question 3 : Marge latente bloquée — Indicateur

**Objectif** : afficher la somme de la marge latente bloquée par les dormants.

1. Cliquer sur **+** > **Nouvelle question**
2. Sélectionner **MEDIcore** > **MART_KPI_DORMANT**
3. Cliquer sur **Résumer** > **Somme de…** > `MARGE_LATENTE_BLOQUEE`
4. Cliquer sur **Filtrer** > `IS_DORMANT_6M` > **true**
5. Cliquer sur **Visualiser** — nombre unique
6. **Enregistrer** sous le nom `Marge latente bloquée`
7. Placer à droite des deux indicateurs précédents (largeur : 8 colonnes)

**Équivalent SQL** :
```sql
SELECT SUM(MARGE_LATENTE_BLOQUEE)
FROM MARTS.MART_KPI_DORMANT
WHERE IS_DORMANT_6M = true
```

### Question 4 : Répartition par statut dormant — Camembert

**Objectif** : visualiser la répartition des produits par statut (actif, 3m, 6m, 12m).

1. Cliquer sur **+** > **Nouvelle question**
2. Sélectionner **MEDIcore** > **MART_KPI_DORMANT**
3. Cliquer sur **Résumer** > **Comptage**
4. Cliquer sur **Regrouper par** > `STATUT_DORMANT`
5. Cliquer sur **Visualiser**
6. Changer la visualisation en **Camembert** (icône camembert dans le sélecteur)
7. **Enregistrer** sous le nom `Répartition par statut dormant`
8. Placer sur la 2e ligne du dashboard, à droite (largeur : 12 colonnes)

**Équivalent SQL** :
```sql
SELECT STATUT_DORMANT, COUNT(*)
FROM MARTS.MART_KPI_DORMANT
GROUP BY STATUT_DORMANT
```

### Question 5 : Dormants par univers — Barres

**Objectif** : barres montrant le nombre de dormants 6m par univers (RX, OTC, PARA).

1. Cliquer sur **+** > **Nouvelle question**
2. Sélectionner **MEDIcore** > **MART_KPI_DORMANT**
3. Cliquer sur **Résumer** > **Comptage**
4. Cliquer sur **Regrouper par** > `UNIVERS`
5. Cliquer sur **Filtrer** > `IS_DORMANT_6M` > **true**
6. Cliquer sur **Visualiser**
7. Changer la visualisation en **Barres** (icône barres verticales)
8. **Enregistrer** sous le nom `Dormants par univers`
9. Placer sur la 2e ligne du dashboard, à gauche (largeur : 12 colonnes)

**Équivalent SQL** :
```sql
SELECT UNIVERS, COUNT(*)
FROM MARTS.MART_KPI_DORMANT
WHERE IS_DORMANT_6M = true
GROUP BY UNIVERS
```

### Question 6 : Top 20 dormants par valeur — Tableau

**Objectif** : tableau détaillé des 20 produits dormants les plus coûteux.

1. Cliquer sur **+** > **Nouvelle question**
2. Sélectionner **MEDIcore** > **MART_KPI_DORMANT**
3. Cliquer sur **Colonnes** (icône colonnes) et sélectionner uniquement :
   - `PRD_NOM`, `FOU_NOM`, `QUANTITE_STOCK`, `VALEUR_STOCK_PA`,
     `JOURS_SANS_VENTE`, `STATUT_DORMANT`
   - Décocher toutes les autres colonnes
4. Cliquer sur **Filtrer** > `IS_DORMANT_6M` > **true**
5. Cliquer sur **Trier** > `VALEUR_STOCK_PA` > **Décroissant**
6. Cliquer sur **Limite de lignes** > **20**
7. Cliquer sur **Visualiser** — le résultat s'affiche en tableau
8. **Enregistrer** sous le nom `Top 20 dormants par valeur`
9. Placer sur la 3e ligne du dashboard en **pleine largeur** (24 colonnes)

**Équivalent SQL** :
```sql
SELECT PRD_NOM, FOU_NOM, QUANTITE_STOCK,
       VALEUR_STOCK_PA, JOURS_SANS_VENTE,
       STATUT_DORMANT
FROM MARTS.MART_KPI_DORMANT
WHERE IS_DORMANT_6M = true
ORDER BY VALEUR_STOCK_PA DESC
LIMIT 20
```

> **Référence KPIs** : §2.14 `mart_kpi_dormant` — capital immobilisé, dormants par univers/fournisseur ([voir KPIs.md](KPIs.md#214-mart_kpi_dormant--produits-sans-vente))

### Filtres du dashboard (déjà configurés)

Le dashboard D11 dispose de 4 filtres globaux, reliés à toutes les questions :

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte                 │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Fournisseur         │ Texte                 │ FOU_NOM                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Univers             │ Texte                 │ UNIVERS                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Statut dormant      │ Texte                 │ STATUT_DORMANT                          │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

Pour ajouter un filtre manuellement sur un autre dashboard :

1. En mode édition du dashboard, cliquer sur l'icône **filtre** (entonnoir)
2. Choisir le type de filtre (ex. **Texte**)
3. Nommer le filtre (ex. `Pharmacie`)
4. Cliquer sur chaque question du dashboard pour relier le filtre à la colonne correspondante
5. Cliquer sur **Enregistrer**

### Disposition finale du dashboard D11

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Ligne 1  │ Capital immobilisé │ Nb dormants 6m  │ Marge latente bloquée  │
│          │ (nombre, 8 col)    │ (nombre, 8 col) │ (nombre, 8 col)        │
├──────────────────────────────────────────────────────────────────────────┤
│ Ligne 2  │ Dormants / univers       │ Répartition statut dormant         │
│          │ (barres, 12 col)         │ (camembert, 12 col)                │
├──────────────────────────────────────────────────────────────────────────┤
│ Ligne 3  │ Top 20 dormants par valeur (tableau, 24 col, pleine largeur)  │
│          │                                                               │
│          │                                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

### Résultat

Le dashboard D11 est accessible à `http://localhost:3000/dashboard/12`.
Il contient 7 questions répondant à : **« Combien de capital dort dans mes étagères ? »**

[↑ Retour au sommaire](#table-des-matières)

---

## 5. Les 15 autres dashboards

Chaque dashboard suit la procédure générale décrite en section 3.
Les filtres listés ci-dessous reflètent l'état actuel des dashboards Metabase.

---

### D1 — Vue d'ensemble pharmacie

**Collection** : Direction Générale
**Table source** : `MART_KPI_SYNTHESE_PHARMACIE`

#### Pourquoi ce dashboard

Le titulaire ouvre ce dashboard chaque matin. En 30 secondes, il sait si sa
pharmacie va bien ou non — tous les voyants au vert = rien à faire, un voyant
rouge = creuser.

#### Questions

┌─────────────────────────┬──────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                │ Configuration Metabase                   │ Visu    │ Équivalent SQL                                                                           │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA mensuel + évolution  │ Colonnes : `MOIS`, `CA_HT`, `CA_HT_A1`,  │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(CA_HT), SUM(CA_HT_A1)`                            │
│                         │ `EVOLUTION_CA_VS_A1`                     │         │ `FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE GROUP BY 1`                                      │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA YTD vs A-1           │ Colonnes : `MOIS`, `CA_HT_YTD`,          │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), MAX(CA_HT_YTD), MAX(CA_HT_YTD_A1)`                    │
│                         │ `CA_HT_YTD_A1`, `EVOLUTION_YTD_VS_A1`    │         │ `FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE GROUP BY 1`                                      │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA 12DM glissants       │ Colonnes : `MOIS`, `CA_HT_12DM`,         │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), MAX(CA_HT_12DM), MAX(CA_HT_12DM_A1)`                  │
│                         │ `CA_HT_12DM_A1`                          │         │ `FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE GROUP BY 1`                                      │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge brute mensuelle   │ Colonnes : `MOIS`, `MARGE_BRUTE`         │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(MARGE_BRUTE)`                                     │
│                         │                                          │         │ `FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE GROUP BY 1`                                      │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de marge           │ Colonnes : `TAUX_MARGE`                  │ Nombre  │ `SELECT AVG(TAUX_MARGE) FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE`                          │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux générique          │ Colonnes : `TAUX_GENERIQUE`              │ Nombre  │ `SELECT AVG(TAUX_GENERIQUE) FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE`                      │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Valeur stock PA         │ Colonnes : `VALEUR_STOCK_PA`             │ Nombre  │ `SELECT SUM(VALEUR_STOCK_PA) FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE`                     │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Ratio stock/CA annuel   │ Colonnes : `RATIO_STOCK_CA_ANNUEL_PCT`   │ Nombre  │ `SELECT AVG(RATIO_STOCK_CA_ANNUEL_PCT) FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE`           │
├─────────────────────────┼──────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Produits dormants 6m    │ Colonnes : `NB_DORMANTS_6M`              │ Nombre  │ `SELECT SUM(NB_DORMANTS_6M) FROM MARTS.MART_KPI_SYNTHESE_PHARMACIE`                      │
└─────────────────────────┴──────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.15 `mart_kpi_synthese_pharmacie` — CA, marge, taux générique, stock, dormants ([voir KPIs.md](KPIs.md#215-mart_kpi_synthese_pharmacie--vue-dashboard-consolidée))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ CA mensuel + évolution (courbe, 12 col)  │ CA YTD vs A-1        │
│        │                                          │ (barres, 12 col)     │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ CA 12DM glissants (courbe, 12 col)  │ Marge brute mensuelle     │
│        │                                     │ (courbe, 12 col)          │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Taux de marge     │ Taux générique    │ Valeur stock PA         │
│        │ (nombre, 8 col)   │ (nombre, 8 col)   │ (nombre, 8 col)         │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Ratio stock/CA annuel (nombre, 12 col) │ Produits dormants 6m   │
│        │                                        │ (nombre, 12 col)       │
└──────────────────────────────────────────────────────────────────────────┘
```
[↑ Retour au sommaire](#table-des-matières)

---


### D2 — Évolution CA

**Collection** : Direction Générale
**Table source** : `MART_KPI_CA_EVOLUTION`

#### Pourquoi ce dashboard

Mon CA progresse-t-il ou régresse-t-il vs A-1 ? La courbe 12DM lisse la
saisonnalité pour montrer la tendance de fond. Décision : investir, embaucher,
ou réduire les coûts.

#### Questions

┌──────────────────────────┬────────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                 │ Configuration Metabase                     │ Visu    │ Équivalent SQL                                                                           │
├──────────────────────────┼────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA mensuel N vs N-1      │ Colonnes : `MOIS`, `CA_HT`, `CA_HT_A1`     │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(CA_HT), AVG(CA_HT_A1)`                            │
│                          │                                            │         │ `FROM MARTS.MART_KPI_CA_EVOLUTION GROUP BY 1`                                            │
├──────────────────────────┼────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Évolution YoY par mois   │ Colonnes : `MOIS`,                         │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(EVOLUTION_CA_HT_VS_A1)`                           │
│                          │ `EVOLUTION_CA_HT_VS_A1`                    │         │ `FROM MARTS.MART_KPI_CA_EVOLUTION GROUP BY 1`                                            │
├──────────────────────────┼────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA YTD cumulé N vs N-1   │ Colonnes : `MOIS`, `CA_HT_YTD`,            │ Aire    │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(CA_HT_YTD), AVG(CA_HT_YTD_A1)`                    │
│                          │ `CA_HT_YTD_A1`                             │         │ `FROM MARTS.MART_KPI_CA_EVOLUTION GROUP BY 1`                                            │
├──────────────────────────┼────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ CA 12DM tendance lissée  │ Colonnes : `MOIS`, `CA_HT_12DM`            │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(CA_HT_12DM)`                                      │
│                          │                                            │         │ `FROM MARTS.MART_KPI_CA_EVOLUTION GROUP BY 1`                                            │
├──────────────────────────┼────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│ Jours de vente par mois  │ Colonnes : `MOIS`, `NB_JOURS_VENTE`        │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(NB_JOURS_VENTE)`                                  │
│                          │                                            │         │ `FROM MARTS.MART_KPI_CA_EVOLUTION GROUP BY 1`                                            │
└──────────────────────────┴────────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.10 `mart_kpi_ca_evolution` — CA mensuel, YTD, 12DM, évolution vs A-1 ([voir KPIs.md](KPIs.md#210-mart_kpi_ca_evolution--évolution-ca-vs-a-1))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte                 │ PHARMACIE_SK                            │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

> Pas de filtre Mois : ce dashboard montre l'évolution temporelle complète (N vs N-1, YTD, 12DM).

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ CA mensuel N vs N-1 (courbe, 12 col)  │ Évolution YoY par mois  │
│        │                                       │ (barres, 12 col)        │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ CA YTD cumulé N vs N-1 (aire, 12 col) │ CA 12DM tendance lissée │
│        │                                       │ (courbe, 12 col)        │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Jours de vente par mois (barres, 24 col, pleine largeur)        │
└──────────────────────────────────────────────────────────────────────────┘
```
[↑ Retour au sommaire](#table-des-matières)

---

### D3 — Trésorerie

**Collection** : Direction Générale
**Tables sources** : `MART_KPI_TRESORERIE` + `FACT_TRESORERIE`
#### Pourquoi ce dashboard

Comment rentre l'argent ? Si le tiers payant représente 70%, la
pharmacie dépend de la Sécu. Le titulaire utilise ce dashboard pour
négocier ses frais bancaires CB et anticiper ses besoins en trésorerie.

#### Questions

┌──────────────────────────────────┬──────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                         │ Configuration Metabase                       │ Visu      │ Équivalent SQL                                                                                       │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA total mensuel                 │ Colonnes : `CA_TOTAL`                        │ Nombre    │ `SELECT SUM(CA_TOTAL) FROM MARTS.MART_KPI_TRESORERIE`                                                │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Panier moyen                     │ Colonnes : `PANIER_MOYEN`                    │ Nombre    │ `SELECT AVG(PANIER_MOYEN) FROM MARTS.MART_KPI_TRESORERIE`                                            │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb factures                      │ Colonnes : `NB_FACTURES`                     │ Nombre    │ `SELECT SUM(NB_FACTURES) FROM MARTS.MART_KPI_TRESORERIE`                                             │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Points fidélité                  │ Colonnes : `POINTS_FIDELITE`                 │ Nombre    │ `SELECT SUM(POINTS_FIDELITE) FROM MARTS.MART_KPI_TRESORERIE`                                         │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge remb. vs non-remb.         │ Colonnes : `MARGE_REMBOURSABLE`,             │ Barres    │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(MARGE_REMBOURSABLE), SUM(MARGE_NON_REMBOURSABLE)`             │
│                                  │ `MARGE_NON_REMBOURSABLE`                     │           │ `FROM MARTS.MART_KPI_TRESORERIE GROUP BY 1`                                                          │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Remises totales                  │ Colonnes : `REMISES_TOTALES`                 │ Nombre    │ `SELECT SUM(REMISES_TOTALES) FROM MARTS.MART_KPI_TRESORERIE`                                         │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Répartition modes de paiement    │ SQL natif : jointure FACT_TRESORERIE,        │ Camembert │ `SELECT 'CB' AS mode, SUM(PCT_CB) UNION ALL SELECT 'Espèces', SUM(PCT_ESPECES) ...`                  │
│                                  │ répartition par mode de paiement             │           │ `FROM MARTS.MART_KPI_TRESORERIE`                                                                     │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Rétrocessions                    │ Colonnes : `MOIS`, `CA_RETROCESSIONS`        │ Courbe    │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(CA_RETROCESSIONS)`                                            │
│                                  │                                              │           │ `FROM MARTS.MART_KPI_TRESORERIE GROUP BY 1`                                                          │
├──────────────────────────────────┼──────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TVA par taux                     │ SQL natif : SUM par taux TVA,                │ Tableau   │ `SELECT DATE_TRUNC('MONTH', DATE_JOUR), SUM(TVA_TAUX1), SUM(TVA_TAUX2), ...`                         │
│                                  │ regroupé par mois                            │           │ `FROM MARTS.FACT_TRESORERIE GROUP BY 1`                                                              │
└──────────────────────────────────┴──────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.5 `mart_kpi_tresorerie` + §1.6 `fact_tresorerie` — panier moyen, paiements, TVA, rétrocessions ([voir KPIs.md](KPIs.md#25-mart_kpi_tresorerie--trésorerie-mensuelle))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ CA total mensuel   │ Panier moyen       │ Nb factures           │
│        │ (nombre, 8 col)    │ (nombre, 8 col)    │ (nombre, 8 col)       │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Points fidélité    │ Marge remb. vs non-remb.                   │
│        │ (nombre, 8 col)    │ (barres, 16 col)                           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Remises totales (nombre, 8 col)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Répartition modes de paiement   │ Rétrocessions                 │
│        │ (camembert, 8 col, SQL natif)   │ (courbe, 16 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=19 │ TVA par taux (tableau, 24 col, SQL natif, pleine largeur)       │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D4 — Marge détaillée

**Collection** : Ventes & Performance
**Tables sources** : `MART_KPI_MARGE` + `MART_KPI_MARGE_PAR_PRODUIT` + `MART_KPI_MARGE_PAR_UNIVERS` + `DIM_PRODUIT`
#### Pourquoi ce dashboard

La marge est la rentabilité réelle — le CA seul ne veut rien dire si
on vend à perte. Le responsable achats identifie les produits
« vaches à lait » et les « pièges » (marges négatives) pour
renégocier les prix d'achat.

#### Questions

┌──────────────────────────────┬──────────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                     │ Configuration Metabase                       │ Visu    │ Équivalent SQL                                                                                   │
├──────────────────────────────┼──────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge brute par jour         │ Colonnes : `DATE_JOUR`, `MARGE_BRUTE`        │ Courbe  │ `SELECT DATE_TRUNC('DAY', DATE_JOUR), SUM(MARGE_BRUTE)`                                          │
│                              │                                              │         │ `FROM MARTS.MART_KPI_MARGE GROUP BY 1`                                                           │
├──────────────────────────────┼──────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Top 20 produits par marge    │ SQL natif : jointure                         │ Barres  │ `SELECT PRD_NOM, SUM(MARGE_BRUTE) FROM MARTS.MART_KPI_MARGE_PAR_PRODUIT`                         │
│                              │ MART_KPI_MARGE_PAR_PRODUIT +                 │         │ `GROUP BY 1 ORDER BY 2 DESC LIMIT 20`                                                            │
│                              │ DIM_PRODUIT, top 20 par marge décroissante   │         │                                                                                                  │
├──────────────────────────────┼──────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de marge par univers    │ SQL natif : jointure                         │ Barres  │ `SELECT UNIVERS, AVG(TAUX_MARGE_PCT) FROM MARTS.MART_KPI_MARGE_PAR_UNIVERS`                      │
│                              │ MART_KPI_MARGE_PAR_UNIVERS +                 │         │ `GROUP BY 1 ORDER BY 2 DESC`                                                                     │
│                              │ DIM_PRODUIT, taux de marge par univers       │         │                                                                                                  │
├──────────────────────────────┼──────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Distribution taux de marge   │ SQL natif : jointure                         │ Barres  │ `SELECT CASE WHEN TAUX_MARGE < 0.10 THEN '0-10%' ... END, COUNT(*)`                              │
│                              │ MART_KPI_MARGE_PAR_PRODUIT +                 │         │ `FROM MARTS.MART_KPI_MARGE GROUP BY 1`                                                           │
│                              │ DIM_PRODUIT, distribution par tranches       │         │                                                                                                  │
├──────────────────────────────┼──────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marges négatives             │ Colonnes : `PRD_NOM`, `TAUX_MARGE`,          │ Tableau │ `SELECT * FROM MARTS.MART_KPI_MARGE WHERE TAUX_MARGE < 0`                                        │
│                              │ `MARGE_BRUTE` > Filtrer `TAUX_MARGE` < 0     │         │ `ORDER BY TAUX_MARGE LIMIT 20`                                                                   │
└──────────────────────────────┴──────────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.1 `mart_kpi_marge` + §2.16 `mart_kpi_marge_par_produit` + §2.17 `mart_kpi_marge_par_univers` — marge par jour/produit/univers ([voir KPIs.md](KPIs.md#21-mart_kpi_marge--marge-journalière))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Univers             │ Texte (= ← pharmacie) │ UNIVERS                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Date                │ Date (plage)          │ DATE_JOUR                               │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Marge brute par jour (courbe, 24 col, pleine largeur)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Top 20 produits par marge (barres, 24 col, SQL natif)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Taux de marge par univers        │ Distribution taux de marge   │
│        │ (barres, 13 col, SQL natif)      │ (barres, 11 col, SQL natif)  │
├──────────────────────────────────────────────────────────────────────────┤
│ row=13 │ Marges négatives (tableau, 24 col, pleine largeur)              │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D5 — Performance vendeurs

**Collection** : Ventes & Performance
**Table source** : `MART_KPI_OPERATEUR`
#### Pourquoi ce dashboard

Chaque vendeur a un profil différent — certains vendent du volume
(ordonnances), d'autres du conseil (parapharmacie à forte marge). Ce
dashboard identifie les forces de chacun pour optimiser le planning,
distribuer les primes, et cibler les formations.

#### Questions

┌─────────────────────────────────┬──────────────────────────────────────────────────┬─────────┬───────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                        │ Configuration Metabase                           │ Visu    │ Équivalent SQL                                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ CA par opérateur                │ Colonnes : `OPERATEUR`, `CA_TTC`                 │ Barres  │ `SELECT OPERATEUR, SUM(CA_TTC) FROM MARTS.MART_KPI_OPERATEUR GROUP BY 1`                  │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ Panier moyen par opérateur      │ Colonnes : `OPERATEUR`, `PANIER_MOYEN`           │ Barres  │ `SELECT OPERATEUR, AVG(PANIER_MOYEN) FROM MARTS.MART_KPI_OPERATEUR GROUP BY 1`            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de marge par opérateur     │ Colonnes : `OPERATEUR`, `TAUX_MARGE`             │ Barres  │ `SELECT OPERATEUR, AVG(TAUX_MARGE) FROM MARTS.MART_KPI_OPERATEUR GROUP BY 1`              │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ % lignes remboursables          │ Colonnes : `OPERATEUR`,                          │ Barres  │ `SELECT OPERATEUR, AVG(PCT_LIGNES_REMBOURSABLES)`                                         │
│                                 │ `PCT_LIGNES_REMBOURSABLES`                       │         │ `FROM MARTS.MART_KPI_OPERATEUR GROUP BY 1`                                                │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ Productivité CA moyen par jour  │ Colonnes : `OPERATEUR`,                          │ Barres  │ `SELECT OPERATEUR, AVG(CA_MOYEN_PAR_JOUR)`                                                │
│                                 │ `CA_MOYEN_PAR_JOUR`                              │         │ `FROM MARTS.MART_KPI_OPERATEUR GROUP BY 1`                                                │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ Heure de pic CA par opérateur   │ Colonnes : `OPERATEUR`, `HEURE_PIC_CA`           │ Tableau │ `SELECT OPERATEUR, HEURE_PIC_CA FROM MARTS.MART_KPI_OPERATEUR`                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb clients/jour par opérateur   │ Colonnes : `OPERATEUR`,                          │ Tableau │ `SELECT OPERATEUR, CA_MOYEN_PAR_JOUR FROM MARTS.MART_KPI_OPERATEUR`                       │
│                                 │ `NB_CLIENTS_PAR_JOUR`                            │         │ `ORDER BY 2 DESC`                                                                         │
└─────────────────────────────────┴──────────────────────────────────────────────────┴─────────┴───────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.8 `mart_kpi_operateur` — CA, panier, marge, productivité par vendeur ([voir KPIs.md](KPIs.md#28-mart_kpi_operateur--performance-opérateur))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Opérateur           │ Texte (= ← pharmacie) │ OPERATEUR                               │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Taux de marge / opérateur       │ Panier moyen / opérateur      │
│        │ (barres, 12 col)                │ (barres, 12 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ CA par opérateur                │ Productivité CA moyen/jour    │
│        │ (barres, 12 col)                │ (barres, 12 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ % lignes remb.     │ Nb clients/jour   │ Heure de pic CA        │
│        │ (barres, 8 col)    │ (tableau, 8 col)  │ (tableau, 8 col)       │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D6 — Univers RX/OTC/PARA

**Collection** : Ventes & Performance
**Table source** : `MART_KPI_UNIVERS`
#### Pourquoi ce dashboard

La pharmacie a 3 métiers : médicaments sur ordonnance (RX), conseil
(OTC), parapharmacie (PARA). Le mix détermine la stratégie : 80%
RX = dépendance Sécu, 40% PARA = plus de marge mais plus de
concurrence internet. Guide l'aménagement de l'officine.

#### Questions

┌───────────────────────────────────┬──────────────────────────────────────────────┬───────────┬─────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                          │ Configuration Metabase                       │ Visu      │ Équivalent SQL                                                                              │
├───────────────────────────────────┼──────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA par univers                    │ Colonnes : `UNIVERS`, `CA_HT`                │ Camembert │ `SELECT UNIVERS, SUM(CA_HT) FROM MARTS.MART_KPI_UNIVERS GROUP BY 1`                         │
├───────────────────────────────────┼──────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de marge par univers         │ Colonnes : `UNIVERS`, `TAUX_MARGE`           │ Barres    │ `SELECT UNIVERS, AVG(TAUX_MARGE) FROM MARTS.MART_KPI_UNIVERS GROUP BY 1`                    │
├───────────────────────────────────┼──────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Mix CA (% par univers)            │  Colonnes : `MOIS`, `UNIVERS`,               │ Barres    │ `SELECT DATE_TRUNC('MONTH', MOIS), UNIVERS, AVG(PCT_CA_UNIVERS)`                            │
│                                   │ `PCT_CA_UNIVERS`                             │           │ `FROM MARTS.MART_KPI_UNIVERS GROUP BY 1, 2`                                                 │
├───────────────────────────────────┼──────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Mix marge (% par univers)         │   Colonnes : `UNIVERS`,                      │ Camembert │ `SELECT UNIVERS, AVG(PCT_MARGE_UNIVERS)`                                                    │
│                                   │ `PCT_MARGE_UNIVERS`                          │           │ `FROM MARTS.MART_KPI_UNIVERS GROUP BY 1`                                                    │
├───────────────────────────────────┼──────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Évolution CA vs A-1 par univers   │ Colonnes : `UNIVERS`,                        │ Tableau   │ `SELECT UNIVERS, CA_HT, CA_HT_A1, EVOLUTION_CA_VS_A1`                                       │
│                                   │ `EVOLUTION_CA_VS_A1`,                        │           │ `FROM MARTS.MART_KPI_UNIVERS`                                                               │
│                                   │ `NB_LABORATOIRES`, `NB_PRODUITS`             │           │                                                                                             │
└───────────────────────────────────┴──────────────────────────────────────────────┴───────────┴─────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.13 `mart_kpi_univers` — CA, marge, mix par univers RX/OTC/PARA ([voir KPIs.md](KPIs.md#213-mart_kpi_univers--kpis-par-univers-dashboard))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ CA par univers (camembert, 9 col)  │ Taux de marge par univers  │
│        │                                    │ (barres, 15 col)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Mix CA (% par univers)             │ Mix marge (% par univers)  │
│        │ (barres, 15 col)                   │ (camembert, 9 col)         │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Évolution CA vs A-1 par univers (tableau, 24 col, pleine larg.) │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D7 — Stock et rotation

**Collection** : Achats & Stock
**Tables sources** : `MART_KPI_STOCK` + `MART_KPI_STOCK_VALORISATION`
#### Pourquoi ce dashboard

Le stock est le plus gros poste de dépense (~200-400k €). Un stock
qui tourne vite = capital libéré. Permet de dimensionner les
commandes : 45 jours de couverture = pas de commande, 3 jours =
commande urgente.

#### Questions

┌───────────────────────────────────┬────────────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                          │ Configuration Metabase                         │ Visu    │ Équivalent SQL                                                                                   │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Rotation stock mensuelle          │ Colonnes : `MOIS`, `ROTATION_STOCK`            │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(ROTATION_STOCK)`                                          │
│                                   │                                                │         │ `FROM MARTS.MART_KPI_STOCK GROUP BY 1`                                                           │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de rupture stock             │ Colonnes : `MOIS`,                             │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(TAUX_RUPTURE_STOCK)`                                      │
│                                   │ `TAUX_RUPTURE_STOCK`                           │         │ `FROM MARTS.MART_KPI_STOCK GROUP BY 1`                                                           │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Valorisation stock PA fin mois    │ Colonnes : `MOIS`,                             │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(VALEUR_STOCK_PA_FIN_MOIS)`                                │
│                                   │ `VALEUR_STOCK_PA_FIN_MOIS`                     │         │ `FROM MARTS.MART_KPI_STOCK_VALORISATION GROUP BY 1`                                              │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Couverture stock en jours         │ Colonnes : `MOIS`,                             │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(COUVERTURE_STOCK_JOURS)`                                  │
│                                   │ `COUVERTURE_STOCK_JOURS`                       │         │ `FROM MARTS.MART_KPI_STOCK_VALORISATION GROUP BY 1`                                              │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge latente moyenne             │ Colonnes : `MARGE_LATENTE_MOYENNE`             │ Nombre  │ `SELECT AVG(MARGE_LATENTE_MOYENNE) FROM MARTS.MART_KPI_STOCK_VALORISATION`                       │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Stock moyen vs ventes             │ Colonnes : `MOIS`, `STOCK_MOYEN`,              │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(STOCK_MOYEN), SUM(QUANTITE_VENDUE)`                       │
│                                   │ `QUANTITE_VENDUE`                              │         │ `FROM MARTS.MART_KPI_STOCK GROUP BY 1`                                                           │
├───────────────────────────────────┼────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Variation prix d'achat            │ Colonnes : `PRD_NOM`,                          │ Tableau │ `SELECT * FROM MARTS.MART_KPI_STOCK_VALORISATION`                                                │
│                                   │ `VARIATION_PRIX_ACHAT`                         │         │ `ORDER BY VARIATION_PRIX_ACHAT DESC LIMIT 20`                                                    │
└───────────────────────────────────┴────────────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.2 `mart_kpi_stock` + §2.6 `mart_kpi_stock_valorisation` — rotation, couverture, valorisation ([voir KPIs.md](KPIs.md#22-mart_kpi_stock--rotation-et-rupture-stock-mensuelles))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Rotation stock mensuelle        │ Taux de rupture stock         │
│        │ (courbe, 12 col)                │ (courbe, 12 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Valorisation stock PA fin mois  │ Couverture stock en jours     │
│        │ (courbe, 12 col)                │ (courbe, 12 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Marge latente moy.  │ Stock moyen vs ventes                     │
│        │ (nombre, 5 col)     │ (barres, 19 col)                          │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Variation prix d'achat (tableau, 24 col, pleine largeur)        │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D8 — Ruptures et CA perdu

**Collection** : Achats & Stock
**Tables sources** : `MART_KPI_RUPTURES` + `MART_KPI_RUPTURES_PAR_PRODUIT` + `DIM_PRODUIT`
#### Pourquoi ce dashboard

Une rupture = un client qui repart sans son médicament. CA perdu +
fidélité détruite. Ce dashboard chiffre le manque à gagner en euros
pour justifier des investissements en stock de sécurité.

#### Questions

┌─────────────────────────────────┬──────────────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                        │ Configuration Metabase                           │ Visu    │ Équivalent SQL                                                                                       │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA estimé perdu par mois        │ Colonnes : `MOIS`, `CA_ESTIME_PERDU`             │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(CA_ESTIME_PERDU)`                                             │
│                                 │                                                  │         │ `FROM MARTS.MART_KPI_RUPTURES GROUP BY 1`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge estimée perdue            │ Colonnes : `MOIS`,                               │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(MARGE_ESTIMEE_PERDUE)`                                        │
│                                 │ `MARGE_ESTIMEE_PERDUE`                           │         │ `FROM MARTS.MART_KPI_RUPTURES GROUP BY 1`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Clients impactés par mois       │ Colonnes : `MOIS`,                               │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(NB_CLIENTS_IMPACTES)`                                         │
│                                 │ `NB_CLIENTS_IMPACTES`                            │         │ `FROM MARTS.MART_KPI_RUPTURES GROUP BY 1`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux de rupture demande         │ Colonnes : `MOIS`,                               │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(TAUX_RUPTURE_DEMANDE)`                                        │
│                                 │ `TAUX_RUPTURE_DEMANDE`                           │         │ `FROM MARTS.MART_KPI_RUPTURES GROUP BY 1`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Top 10 produits en rupture      │ Table `MART_KPI_RUPTURES_PAR_PRODUIT`            │ Barres  │ `SELECT PRD_NOM, SUM(NB_BOITES_MANQUANTES) FROM MARTS.MART_KPI_RUPTURES_PAR_PRODUIT`                  │
│                                 │ Colonnes : `PRD_NOM`,                            │         │ `GROUP BY 1 ORDER BY 2 DESC LIMIT 10`                                                                │
│                                 │ `NB_BOITES_MANQUANTES`                           │         │                                                                                                      │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Jours de rupture par produit    │ Table `MART_KPI_RUPTURES_PAR_PRODUIT`            │ Tableau │ `SELECT PRD_NOM, MOIS, SUM(NB_JOURS_RUPTURE) FROM MARTS.MART_KPI_RUPTURES_PAR_PRODUIT`                │
│                                 │ Colonnes : `PRD_NOM`, `MOIS`,                    │         │ `GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20`                                                             │
│                                 │ `NB_JOURS_RUPTURE`                               │         │                                                                                                      │
└─────────────────────────────────┴──────────────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.4 `mart_kpi_ruptures` + §2.18 `mart_kpi_ruptures_par_produit` — CA perdu, clients impactés, top produits ([voir KPIs.md](KPIs.md#24-mart_kpi_ruptures--impact-des-ruptures-et-ca-perdu))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ CA estimé perdu par mois (barres, 24 col, pleine largeur)       │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Marge estimée perdue (courbe, 24 col, pleine largeur)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Clients impactés par mois (courbe, 24 col, pleine largeur)      │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Taux de rupture demande (courbe, 24 col, pleine largeur)        │
├──────────────────────────────────────────────────────────────────────────┤
│ row=16 │ Top 10 produits en rupture     │ Jours de rupture par produit   │
│        │ (barres, 14 col, SQL natif)    │ (tableau, 10 col, SQL natif)   │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D9 — Écoulement (sell-through)

**Collection** : Achats & Stock
**Tables sources** : `MART_KPI_ECOULEMENT` + `MART_KPI_ECOULEMENT_PAR_FOURNISSEUR` + `DIM_PRODUIT` + `DIM_FOURNISSEUR`
#### Pourquoi ce dashboard

J'achète 100 boîtes et j'en vends 40 → taux d'écoulement 40% → je
sur-commande. Identifie les fournisseurs qui « poussent » du volume
et les produits sur-stockés.

#### Questions

┌────────────────────────────────────┬──────────────────────────────────────────────────┬─────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                           │ Configuration Metabase                           │ Visu    │ Équivalent SQL                                                                                        │
├────────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux d'écoulement mensuel          │ Colonnes : `MOIS`, `TAUX_ECOULEMENT`             │ Courbe  │ `SELECT DATE_TRUNC('MONTH', MOIS), AVG(TAUX_ECOULEMENT)`                                              │
│                                    │                                                  │         │ `FROM MARTS.MART_KPI_ECOULEMENT GROUP BY 1`                                                           │
├────────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Commandé vs vendu par mois         │ Colonnes : `MOIS`,                               │ Barres  │ `SELECT DATE_TRUNC('MONTH', MOIS), SUM(QUANTITE_COMMANDEE), SUM(QUANTITE_VENDUE)`                     │
│                                    │ `QUANTITE_COMMANDEE`, `QUANTITE_VENDUE`          │         │ `FROM MARTS.MART_KPI_ECOULEMENT GROUP BY 1`                                                           │
├────────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Produits sur-stockés (taux < 50%)  │   Colonnes : `PRD_NOM`,                          │ Tableau │ `SELECT * FROM MARTS.MART_KPI_ECOULEMENT WHERE TAUX_ECOULEMENT < 50`                                  │
│                                    │ `QUANTITE_COMMANDEE`,                            │         │ `ORDER BY TAUX_ECOULEMENT LIMIT 20`                                                                   │
│                                    │ `QUANTITE_VENDUE`, `TAUX_ECOULEMENT`             │         │                                                                                                       │
│                                    │ Filtrer > `TAUX_ECOULEMENT` < 50                 │         │                                                                                                       │
├────────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Écoulement par fournisseur         │ Table `MART_KPI_ECOULEMENT_PAR_FOURNISSEUR`      │ Barres  │ `SELECT FOU_NOM, AVG(TAUX_ECOULEMENT) FROM MARTS.MART_KPI_ECOULEMENT_PAR_FOURNISSEUR`                  │
│                                    │ Colonnes : `FOU_NOM`,                            │         │ `WHERE TAUX_ECOULEMENT IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 15`                               │
│                                    │ `TAUX_ECOULEMENT` (pondéré)                      │         │                                                                                                       │
└────────────────────────────────────┴──────────────────────────────────────────────────┴─────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.3 `mart_kpi_ecoulement` + §2.19 `mart_kpi_ecoulement_par_fournisseur` — taux d'écoulement produit et fournisseur ([voir KPIs.md](KPIs.md#23-mart_kpi_ecoulement--taux-découlement-mensuel))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

> Pas de filtre Fournisseur au niveau du dashboard — le filtre fournisseur est intégré dans la requête SQL natif de la card « Écoulement par fournisseur ».

#### Disposition

```
┌────────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Taux d'écoulement mensuel    │ Commandé vs vendu par mois         │
│        │ (courbe, 12 col)             │ (barres, 12 col)                   │
├────────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Produits sur-stockés (taux < 50%) (tableau, 24 col, pleine larg.) │
├────────────────────────────────────────────────────────────────────────────┤
│ row=9  │ Écoulement par fournisseur (barres, 24 col, SQL natif)            │
└────────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D10 — Remises fournisseurs

**Collection** : Achats & Stock
**Table source** : `MART_KPI_REMISE_LABO`
#### Pourquoi ce dashboard

Les remises fournisseurs sont un levier de marge considérable.
Compare la remise « catalogue » (simple) vs la remise « réelle »
(pondérée par volume). Un labo qui baisse ses remises vs A-1 =
signal de renégociation.

#### Questions

┌─────────────────────────────────────┬──────────────────────────────────────────────────┬───────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                            │ Configuration Metabase                           │ Visu      │ Équivalent SQL                                                                                      │
├─────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Remise pondérée par labo            │ Colonnes : `FOU_NOM`,                            │ Barres    │ `SELECT FOU_NOM, AVG(REMISE_PONDEREE_MONTANT)`                                                      │
│                                     │ `REMISE_PONDEREE_MONTANT`                        │           │ `FROM MARTS.MART_KPI_REMISE_LABO GROUP BY 1 ORDER BY 2 DESC LIMIT 15`                               │
├─────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PDM achats par labo                 │ Colonnes : `FOU_NOM`, `PDM_ACHATS_LABO`          │ Camembert │ `SELECT FOU_NOM, AVG(PDM_ACHATS_LABO) FROM MARTS.MART_KPI_REMISE_LABO GROUP BY 1`                   │
├─────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Remise simple vs pondérée           │ Colonnes : `FOU_NOM`, `REMISE_MOYENNE`,          │ Tableau   │ `SELECT FOU_NOM, REMISE_MOYENNE, REMISE_PONDEREE_QTE, REMISE_PONDEREE_MONTANT`                      │
│                                     │ `REMISE_PONDEREE_QTE`                            │           │ `FROM MARTS.MART_KPI_REMISE_LABO LIMIT 20`                                                          │
├─────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Montant achats par labo + évolution │ Colonnes : `FOU_NOM`, `MONTANT_TOTAL`,           │ Tableau   │ `SELECT FOU_NOM, MONTANT_TOTAL, EVOLUTION_MONTANT_VS_A1`                                            │
│                                     │ `EVOLUTION_MONTANT_VS_A1`                        │           │ `FROM MARTS.MART_KPI_REMISE_LABO ORDER BY 2 DESC LIMIT 20`                                          │
├─────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Évolution remise vs A-1             │ Colonnes : `FOU_NOM`,                            │ Tableau   │ `SELECT FOU_NOM, REMISE_PONDEREE_MONTANT, EVOLUTION_REMISE_VS_A1, MONTANT_TOTAL`                    │
│                                     │ `REMISE_PONDEREE_MONTANT`,                       │           │ `FROM MARTS.MART_KPI_REMISE_LABO LIMIT 20`                                                          │
│                                     │ `EVOLUTION_REMISE_VS_A1`, `MONTANT_TOTAL`        │           │                                                                                                     │
└─────────────────────────────────────┴──────────────────────────────────────────────────┴───────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.12 `mart_kpi_remise_labo` — remise pondérée, PDM achats, évolution vs A-1 ([voir KPIs.md](KPIs.md#212-mart_kpi_remise_labo--remise-pondérée-par-laboratoire))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Fournisseur         │ Texte (= ← pharmacie) │ FOU_NOM                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Remise pondérée par labo       │ PDM achats par labo            │
│        │ (barres, 12 col)               │ (camembert, 12 col)            │
├──────────────────────────────────────────────────────────────────────────┤
│ row=5  │ Remise simple vs pondérée      │ Montant achats par labo        │
│        │ (tableau, 14 col)              │ + évolution (tableau, 10 col)  │
├──────────────────────────────────────────────────────────────────────────┤
│ row=10 │ Évolution remise vs A-1 (tableau, 24 col, pleine largeur)       │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D12 — Classification ABC (Pareto)

**Collection** : Qualité & Pilotage
**Table source** : `MART_KPI_ABC`
#### Pourquoi ce dashboard

20% des produits font 80% du CA (Pareto). Les produits « A » ne
doivent jamais être en rupture. Les produits « C » peuvent être
déréférencés si dormants. Guide la stratégie de référencement et
d'approvisionnement.

#### Questions

┌──────────────────────────┬──────────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                 │ Configuration Metabase                           │ Visu      │ Équivalent SQL                                                                               │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb produits classe A     │ Colonnes : comptage filtré `CLASSE_ABC` = A      │ Nombre    │ `SELECT COUNT(*) FROM MARTS.MART_KPI_ABC WHERE CLASSE_ABC = 'A'`                             │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb produits classe B     │ Colonnes : comptage filtré `CLASSE_ABC` = B      │ Nombre    │ `SELECT COUNT(*) FROM MARTS.MART_KPI_ABC WHERE CLASSE_ABC = 'B'`                             │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb produits classe C     │ Colonnes : comptage filtré `CLASSE_ABC` = C      │ Nombre    │ `SELECT COUNT(*) FROM MARTS.MART_KPI_ABC WHERE CLASSE_ABC = 'C'`                             │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Répartition A/B/C        │ Colonnes : `CLASSE_ABC`, comptage                │ Camembert │ `SELECT CLASSE_ABC, COUNT(*) FROM MARTS.MART_KPI_ABC GROUP BY 1`                             │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA par classe ABC        │ Colonnes : `CLASSE_ABC`, `CA_HT`                 │ Barres    │ `SELECT CLASSE_ABC, SUM(CA_HT) FROM MARTS.MART_KPI_ABC GROUP BY 1`                           │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Courbe de Pareto         │ Colonnes : `RANG`, `PCT_CA_CUMULE`               │ Courbe    │ `SELECT RANG, AVG(PCT_CA_CUMULE) FROM MARTS.MART_KPI_ABC GROUP BY 1`                         │
├──────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Top 10 produits A        │ Colonnes : `RANG`, `PRD_NOM`, `CA_HT`,           │ Tableau   │ `SELECT RANG, PRODUIT_SK, CA_HT, PCT_CA, PCT_CA_CUMULE`                                      │
│                          │ `PCT_CA`, `PCT_CA_CUMULE`                        │           │ `FROM MARTS.MART_KPI_ABC WHERE CLASSE_ABC = 'A' ORDER BY RANG LIMIT 10`                      │
│                          │ Filtrer `CLASSE_ABC` = A > Limite 10             │           │                                                                                              │
└──────────────────────────┴──────────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.9 `mart_kpi_abc` — classification Pareto, courbe ABC, top produits A ([voir KPIs.md](KPIs.md#29-mart_kpi_abc--classification-pareto))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Nb produits A     │ Nb produits B     │ Nb produits C           │
│        │ (nombre, 8 col)   │ (nombre, 8 col)   │ (nombre, 8 col)         │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Répartition A/B/C              │ CA par classe ABC              │
│        │ (camembert, 12 col)            │ (barres, 12 col)               │
├──────────────────────────────────────────────────────────────────────────┤
│ row=9  │ Courbe de Pareto       │ Top 10 produits A                      │
│        │ (courbe, 9 col)        │ (tableau, 15 col)                      │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D13 — Génériques et labos

**Collection** : Qualité & Pilotage
**Tables sources** : `MART_KPI_GENERIQUE` + `MART_KPI_GENERIQUE_MARGE`
#### Pourquoi ce dashboard

L'objectif CPAM de 80% de génériques est un impératif
réglementaire — en dessous, pénalités financières. Suit la
conformité et identifie les opportunités : substituer un princeps
par un générique = meilleure marge + conformité.

#### Questions

┌─────────────────────────────────┬──────────────────────────────────────────────────┬─────────┬──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                        │ Configuration Metabase                           │ Visu    │ Équivalent SQL                                                                                   │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux générique pharmacie        │ Colonnes : `TAUX_GENERIQUE_PHARMACIE`            │ Nombre  │ `SELECT AVG(TAUX_GENERIQUE_PHARMACIE) FROM MARTS.MART_KPI_GENERIQUE`                             │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA générique vs princeps        │ Colonnes : `TYPE_PRODUIT`, `CA_HT`               │ Barres  │ `SELECT IS_GENERIQUE, SUM(CA_HT) FROM MARTS.MART_KPI_GENERIQUE GROUP BY 1`                       │
│                                 │ (table MART_KPI_GENERIQUE_MARGE)                 │         │                                                                                                  │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PDM par labo top 15             │ Colonnes : `FOU_NOM`, `PDM_LABO`                 │ Barres  │ `SELECT FOU_NOM, AVG(PDM_LABO) FROM MARTS.MART_KPI_GENERIQUE`                                    │
│                                 │ Trier desc > Limite 15                           │         │ `GROUP BY 1 ORDER BY 2 DESC LIMIT 15`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb produits par labo            │ Colonnes : `FOU_NOM`, `NB_PRODUITS`              │ Barres  │ `SELECT FOU_NOM, SUM(NB_PRODUITS) FROM MARTS.MART_KPI_GENERIQUE`                                 │
│                                 │                                                  │         │ `GROUP BY 1 ORDER BY 2 DESC LIMIT 15`                                                            │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Évolution CA par labo vs A-1    │ Colonnes : `FOU_NOM`, `CA_HT`,                   │ Tableau │ `SELECT FOU_NOM, CA_HT, CA_HT_A1, EVOLUTION_VS_A1`                                               │
│                                 │ `EVOLUTION_CA_VS_A1`, `MARGE_BRUTE`,             │         │ `FROM MARTS.MART_KPI_GENERIQUE LIMIT 20`                                                         │
│                                 │ `EVOLUTION_MARGE_VS_A1`                          │         │                                                                                                  │
├─────────────────────────────────┼──────────────────────────────────────────────────┼─────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge générique vs princeps     │ Colonnes : `TYPE_PRODUIT`, `TAUX_MARGE`          │ Barres  │ `SELECT TYPE_PRODUIT, AVG(TAUX_MARGE)`                                                           │
│                                 │ (table MART_KPI_GENERIQUE_MARGE)                 │         │ `FROM MARTS.MART_KPI_GENERIQUE_MARGE GROUP BY 1`                                                 │
└─────────────────────────────────┴──────────────────────────────────────────────────┴─────────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.11 `mart_kpi_generique` + §2.21 `mart_kpi_generique_marge` — taux générique, PDM labo, marge gen. vs princeps ([voir KPIs.md](KPIs.md#211-mart_kpi_generique--génériques-et-parts-de-marché-labo))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Fournisseur         │ Texte (= ← pharmacie) │ FOU_NOM                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Univers             │ Texte (= ← pharmacie) │ UNIVERS                                 │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Mois                │ Date (mois/année)     │ MOIS                                    │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Taux générique pharmacie    │ Évolution CA par labo vs A-1      │
│        │ (nombre, 10 col)            │ (tableau, 14 col)                 │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ PDM par labo top 15 (barres, 24 col, pleine largeur)            │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Nb produits par labo (barres, 24 col, pleine largeur)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Marge générique vs princeps  │ CA générique vs princeps         │
│        │ (barres, 14 col)             │ (barres, 10 col)                 │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D14 — Qualité des données

**Collection** : Qualité & Pilotage
**Table source** : `MART_KPI_QUALITE_DONNEES`
#### Pourquoi ce dashboard

Un dashboard qui affiche des chiffres faux est pire que pas de
dashboard. Répond à : « Puis-je faire confiance aux chiffres ? »
Le DSI priorise les interventions techniques avec ce dashboard.

#### Questions

┌───────────────────────────────────┬──────────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                          │ Configuration Metabase                           │ Visu      │ Équivalent SQL                                                                                       │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Taux pharmacies OK                │ Colonnes : `TAUX_PHARMACIES_OK`                  │ Nombre    │ `SELECT AVG(TAUX_PHARMACIES_OK) FROM MARTS.MART_KPI_QUALITE_DONNEES`                                 │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb erreurs total                  │ Colonnes : `NB_ERREURS_TOTAL`                    │ Nombre    │ `SELECT SUM(NB_ERREURS_TOTAL) FROM MARTS.MART_KPI_QUALITE_DONNEES`                                   │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Répartition OK/Alerte/Critique    │ Colonnes : `STATUT_FRAICHEUR`, comptage          │ Camembert │ `SELECT STATUT_FRAICHEUR, COUNT(*) FROM MARTS.MART_KPI_QUALITE_DONNEES GROUP BY 1`                   │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Fraîcheur par pharmacie           │ Colonnes : `PHA_NOM`, `DERNIERE_SYNC`,           │ Tableau   │ `SELECT PHA_NOM, DERNIERE_SYNC, HEURES_DEPUIS_SYNC, STATUT_FRAICHEUR`                                │
│                                   │ `HEURES_DEPUIS_SYNC`, `STATUT_FRAICHEUR`         │           │ `FROM MARTS.MART_KPI_QUALITE_DONNEES ORDER BY 3 DESC`                                                │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Erreurs récentes                  │ Colonnes : détail des erreurs récentes           │ Tableau   │ `SELECT PHA_NOM, NB_ERREURS_TOTAL, DERNIERE_ERREUR`                                                  │
│                                   │                                                  │           │ `FROM MARTS.MART_KPI_QUALITE_DONNEES ORDER BY 2 DESC`                                                │
├───────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Nb pharmacies en alerte           │ Colonnes : comptage pharmacies en alerte         │ Nombre    │ `SELECT COUNT(*) FROM MARTS.MART_KPI_QUALITE_DONNEES`                                                │
│                                   │                                                  │           │ `WHERE STATUT_FRAICHEUR IN ('ALERTE', 'CRITIQUE')`                                                   │
└───────────────────────────────────┴──────────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §2.7 `mart_kpi_qualite_donnees` — fraîcheur, erreurs, taux pharmacies OK ([voir KPIs.md](KPIs.md#27-mart_kpi_qualite_donnees--monitoring-pipeline))

#### Filtres

Aucun filtre — ce dashboard est une vue globale de l'état de santé des données.

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Taux pharmacies OK (nombre, 9 col) │ Nb erreurs total           │
│        │                                    │ (nombre, 9 col)            │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Répartition OK/Alerte/Critique  │ Fraîcheur par pharmacie       │
│        │ (camembert, 9 col)              │ (tableau, 9 col)              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Erreurs récentes (tableau, 18 col)                              │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Nb pharmacies en alerte (nombre, 18 col)                        │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D15 — Détail transactions (drill-down)

**Collection** : Détail opérationnel
**Tables sources** : `FACT_VENTES` + `FACT_COMMANDES` + `MART_KPI_VENTES_PAR_PRODUIT`
#### Pourquoi ce dashboard

Quand un chiffre semble anormal sur un dashboard stratégique, le
data analyst descend ici pour investiguer transaction par
transaction. C'est le « microscope » — pas pour la direction, mais
pour comprendre le « pourquoi » derrière un KPI qui dérape.

#### Questions

┌───────────────────────────────┬──────────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                      │ Configuration Metabase                           │ Visu      │ Équivalent SQL                                                                                       │
├───────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Ventes par jour               │ Colonnes : `DATE_VENTE`, `CA_HT`                 │ Courbe    │ `SELECT DATE_TRUNC('DAY', DATE_VENTE), SUM(CA_HT)`                                                   │
│                               │                                                  │           │ `FROM MARTS.FACT_VENTES GROUP BY 1`                                                                  │
├───────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Ventes par sexe               │ Colonnes : `ORD_CLIENT_SEX`, `CA_TTC`            │ Camembert │ `SELECT ORD_CLIENT_SEX, SUM(CA_TTC) FROM MARTS.FACT_VENTES GROUP BY 1`                               │
├───────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Commandes par fournisseur     │ Colonnes : `FOU_NOM`, `MONTANT_PAHTNET`          │ Barres    │ `SELECT FOURNISSEUR_SK, SUM(MONTANT_PAHTNET)`                                                        │
│                               │                                                  │           │ `FROM MARTS.FACT_COMMANDES GROUP BY 1 LIMIT 15`                                                      │
├───────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Top produits vendus           │ SQL natif : jointure                             │ Barres    │ `SELECT PRD_NOM, SUM(QUANTITE_VENDUE) FROM MARTS.MART_KPI_VENTES_PAR_PRODUIT`                        │
│                               │ MART_KPI_VENTES_PAR_PRODUIT,                     │           │ `GROUP BY 1 ORDER BY 2 DESC LIMIT 20`                                                                │
│                               │ top produits par quantité vendue                 │           │                                                                                                      │
├───────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CA par tranche d'âge          │ SQL natif : CA par tranche d'âge client          │ Barres    │ `SELECT CASE WHEN AGE < 216 THEN '0-17' ... END, SUM(CA_TTC)`                                        │
│                               │                                                  │           │ `FROM MARTS.FACT_VENTES GROUP BY 1 ORDER BY 2 DESC`                                                  │
└───────────────────────────────┴──────────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §1.1 `fact_ventes` + §1.2 `fact_commandes` + §2.20 `mart_kpi_ventes_par_produit` — ventes, commandes, profil client ([voir KPIs.md](KPIs.md#11-fact_ventes--ventes-quotidiennes))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Date                │ Date (plage)          │ DATE_VENTE / DATE_COMMANDE              │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Ventes par jour (courbe, 24 col, pleine largeur)                │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Ventes par sexe           │ Commandes par fournisseur           │
│        │ (camembert, 9 col)        │ (barres, 15 col)                    │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Top produits vendus         │ CA par tranche d'âge              │
│        │ (barres, 12 col, SQL natif) │ (barres, 12 col, SQL natif)       │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### D16 — Prix et mouvements stock

**Collection** : Détail opérationnel
**Tables sources** : `FACT_PRIX_JOURNALIER` + `FACT_STOCK_MOUVEMENT`
#### Pourquoi ce dashboard

L'inflation des prix d'achat grignote la marge sans que personne ne
s'en rende compte. Traque l'évolution du prix d'achat produit par
produit et les mouvements physiques du stock. Détecte les hausses
silencieuses pour renégocier avant que la marge ne s'effondre.

#### Questions

┌────────────────────────────────────┬──────────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Question                           │ Configuration Metabase                           │ Visu      │ Équivalent SQL                                                                                       │
├────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Évolution prix tarif/public/achat  │ Colonnes : `DATE_PRIX`, `PRIX_TARIF`,            │ Courbe    │ `SELECT DATE_TRUNC('DAY', DATE_PRIX), AVG(PRIX_TARIF), AVG(PRIX_PUBLIC), AVG(PRIX_ACHAT_NET)`        │
│ net                                │ `PRIX_PUBLIC`, `PRIX_ACHAT_NET`                  │           │ `FROM MARTS.FACT_PRIX_JOURNALIER GROUP BY 1`                                                         │
│                                    │ > multi-courbe                                   │           │                                                                                                      │
├────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Marge brute unitaire               │ Colonnes : `DATE_PRIX`,                          │ Courbe    │ `SELECT DATE_TRUNC('DAY', DATE_PRIX), AVG(MARGE_BRUTE_UNITAIRE)`                                     │
│                                    │ `MARGE_BRUTE_UNITAIRE`                           │           │ `FROM MARTS.FACT_PRIX_JOURNALIER GROUP BY 1`                                                         │
├────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Mouvements stock par jour          │ Colonnes : `DATE_MOUVEMENT`, `DELTA_STOCK`       │ Barres    │ `SELECT DATE_TRUNC('DAY', DATE_MOUVEMENT), SUM(DELTA_STOCK)`                                         │
│                                    │ (table FACT_STOCK_MOUVEMENT)                     │           │ `FROM MARTS.FACT_STOCK_MOUVEMENT GROUP BY 1`                                                         │
├────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Type opération stock               │ Colonnes : `TYPE_OPERATION`, comptage            │ Camembert │ `SELECT TYPE_OPERATION, COUNT(*) FROM MARTS.FACT_STOCK_MOUVEMENT GROUP BY 1`                         │
│                                    │ (table FACT_STOCK_MOUVEMENT)                     │           │                                                                                                      │
├────────────────────────────────────┼──────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Niveau stock après mouvement       │ Colonnes : `DATE_MOUVEMENT`, `STOCK_APRES`       │ Courbe    │ `SELECT DATE_TRUNC('DAY', DATE_MOUVEMENT), AVG(STOCK_APRES)`                                         │
│                                    │ (table FACT_STOCK_MOUVEMENT)                     │           │ `FROM MARTS.FACT_STOCK_MOUVEMENT GROUP BY 1`                                                         │
└────────────────────────────────────┴──────────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────┘

> **Référence KPIs** : §1.3 `fact_prix_journalier` + §1.4 `fact_stock_mouvement` — prix, marge unitaire, mouvements stock ([voir KPIs.md](KPIs.md#13-fact_prix_journalier--évolution-des-prix))

#### Filtres

┌─────────────────────┬───────────────────────┬─────────────────────────────────────────┐
│ Filtre              │ Type                  │ Colonne reliée                          │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Pharmacie           │ Texte (=)             │ PHARMACIE_SK                            │
├─────────────────────┼───────────────────────┼─────────────────────────────────────────┤
│ Date                │ Date (plage)          │ DATE_PRIX / DATE_MOUVEMENT              │
└─────────────────────┴───────────────────────┴─────────────────────────────────────────┘

#### Disposition

```
┌──────────────────────────────────────────────────────────────────────────┐
│ row=0  │ Évolution prix tarif/public/achat net (courbe, 24 col)          │
├──────────────────────────────────────────────────────────────────────────┤
│ row=4  │ Marge brute unitaire (courbe, 24 col, pleine largeur)           │
├──────────────────────────────────────────────────────────────────────────┤
│ row=8  │ Mouvements stock par jour       │ Type opération stock          │
│        │ (barres, 15 col)                │ (camembert, 9 col)            │
├──────────────────────────────────────────────────────────────────────────┤
│ row=12 │ Niveau stock après mouvement (courbe, 24 col, pleine largeur)   │
└──────────────────────────────────────────────────────────────────────────┘
```

[↑ Retour au sommaire](#table-des-matières)

---


### Synthèse des filtres par dashboard

┌──────┬─────────────────────────────────┬────────────┬──────┬─────────────┬─────────┬────────────────┐
│  #   │ Dashboard                       │ Pharmacie  │ Mois │ Fournisseur │ Univers │ Autre          │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D1  │ Vue d'ensemble pharmacie        │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D2  │ Évolution CA                    │     ✓      │      │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D3  │ Trésorerie                      │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D4  │ Marge détaillée                 │     ✓      │      │             │    ✓   │ date           │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D5  │ Performance vendeurs            │     ✓      │  ✓  │             │         │ opérateur      │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D6  │ Univers RX/OTC/PARA             │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D7  │ Stock et rotation               │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D8  │ Ruptures et CA perdu            │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│  D9  │ Écoulement                      │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D10  │ Remises fournisseurs            │     ✓      │  ✓  │      ✓      │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D11  │ Produits dormants               │     ✓      │      │      ✓     │    ✓    │ statut_dormant │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D12  │ Classification ABC              │     ✓      │  ✓  │             │         │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D13  │ Génériques et labos             │     ✓      │  ✓  │      ✓      │    ✓    │                │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D14  │ Qualité des données             │            │      │             │         │ aucun          │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D15  │ Détail transactions             │     ✓      │      │             │         │ date           │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│ D16  │ Prix et mouvements stock        │     ✓      │      │             │         │ date           │
├──────┼─────────────────────────────────┼────────────┼──────┼─────────────┼─────────┼────────────────┤
│      │ **Total**                       │   **15**   │**10**│    **3**    │  **3**  │ opérateur: 1   │
│      │                                 │            │      │             │         │ statut_dorm: 1 │
│      │                                 │            │      │             │         │ date: 3        │
└──────┴─────────────────────────────────┴────────────┴──────┴─────────────┴─────────┴────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## 6. Référentiel Collection → Dashboard → Card (98 cards)

> Pour accéder à une card dans Metabase : Collection → Dashboard → cliquer sur la card pour voir sa requête.

┌─────────────────────┬────────────────────────────────┬─────┬────────────────────────────────────────────┬───────────┬──────────────────────────────────┬──────────────────────────────────────────────────────────────┐
│ Collection          │ Dashboard                      │ ID  │ Card                                       │ Visu      │ Table(s) MARTS                   │ Description                                                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 348 │ CA mensuel + évolution                     │ Courbe    │ MART_KPI_SYNTHESE_PHARMACIE      │ CA HT mensuel et évolution vs A-1                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 349 │ CA YTD vs A-1                              │ Barres    │ MART_KPI_SYNTHESE_PHARMACIE      │ CA cumulé année courante vs précédente                       │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 350 │ CA 12DM glissants                          │ Courbe    │ MART_KPI_SYNTHESE_PHARMACIE      │ CA sur les 12 derniers mois glissants                        │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 351 │ Marge brute mensuelle                      │ Courbe    │ MART_KPI_SYNTHESE_PHARMACIE      │ Marge brute en euros par mois                                │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 352 │ Taux de marge                              │ Nombre    │ MART_KPI_SYNTHESE_PHARMACIE      │ Taux de marge brute en pourcentage                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 353 │ Taux générique                             │ Nombre    │ MART_KPI_SYNTHESE_PHARMACIE      │ Taux de substitution générique vs CPAM 80%                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 354 │ Valeur stock PA                            │ Nombre    │ MART_KPI_SYNTHESE_PHARMACIE      │ Valeur du stock au prix d'achat                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 355 │ Ratio stock/CA annuel                      │ Nombre    │ MART_KPI_SYNTHESE_PHARMACIE      │ Ratio valeur stock vs CA annualisé                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D1 - Synthèse pharmacie        │ 356 │ Produits dormants 6m                       │ Nombre    │ MART_KPI_SYNTHESE_PHARMACIE      │ Nb produits sans vente depuis 6 mois                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D2 - Évolution CA              │  38 │ CA mensuel N vs N-1                        │ Courbe    │ MART_KPI_CA_EVOLUTION            │ CA HT mensuel année courante vs précédente                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D2 - Évolution CA              │  39 │ Évolution YoY par mois                     │ Barres    │ MART_KPI_CA_EVOLUTION            │ % évolution du CA mois par mois                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D2 - Évolution CA              │  40 │ CA YTD cumulé N vs N-1                     │ Aire      │ MART_KPI_CA_EVOLUTION            │ CA cumulé depuis janvier N vs N-1                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D2 - Évolution CA              │  41 │ CA 12DM tendance lissée                    │ Courbe    │ MART_KPI_CA_EVOLUTION            │ Tendance CA 12 derniers mois glissants                       │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D2 - Évolution CA              │  42 │ Jours de vente par mois                    │ Barres    │ MART_KPI_CA_EVOLUTION            │ Nb jours d'activité par mois                                 │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  43 │ CA total mensuel                           │ Nombre    │ MART_KPI_TRESORERIE              │ CA total par mois                                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  45 │ Panier moyen                               │ Nombre    │ MART_KPI_TRESORERIE              │ Montant moyen par transaction                                │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  47 │ Nb factures                                │ Nombre    │ MART_KPI_TRESORERIE              │ Nombre de factures émises                                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  49 │ Répartition modes de paiement              │ Camembert │ MART_KPI_TRESORERIE              │ Ventilation CB, espèces, chèques, TP, virement               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  51 │ Marge remb. vs non-remb.                   │ Barres    │ MART_KPI_TRESORERIE              │ Marge produits remboursables vs non remboursables            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  53 │ Rétrocessions                              │ Courbe    │ MART_KPI_TRESORERIE              │ Montant des rétrocessions                                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  54 │ Points fidélité                            │ Nombre    │ MART_KPI_TRESORERIE              │ Total des points fidélité accordés                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │  57 │ Remises totales                            │ Nombre    │ MART_KPI_TRESORERIE              │ Montant total des remises accordées                          │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Direction Générale  │ D3 - Trésorerie                │ 366 │ TVA par taux                               │ Tableau   │ FACT_TRESORERIE                  │ Ventilation TVA par taux applicable                          │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D4 - Marge détaillée           │  62 │ Marge brute par jour                       │ Courbe    │ MART_KPI_MARGE                   │ Évolution de la marge brute quotidienne                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D4 - Marge détaillée           │  68 │ Marges négatives                           │ Tableau   │ MART_KPI_MARGE                   │ Produits vendus avec une marge négative                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D4 - Marge détaillée           │ 367 │ Top 20 produits par marge                   │ Barres    │ MART_KPI_MARGE_PAR_PRODUIT       │ Les 20 produits générant le plus de marge                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D4 - Marge détaillée           │ 369 │ Distribution taux de marge                 │ Barres    │ MART_KPI_MARGE                   │ Histogramme répartition des taux de marge                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D4 - Marge détaillée           │ 407 │ Taux de marge par univers                  │ Barres    │ MART_KPI_MARGE, DIM_PRODUIT      │ Taux de marge par univers (RX, OTC, PARA)                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  73 │ CA par opérateur                           │ Barres    │ MART_KPI_OPERATEUR               │ CA par vendeur                                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  77 │ Panier moyen par opérateur                 │ Barres    │ MART_KPI_OPERATEUR               │ Montant moyen par transaction par vendeur                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  80 │ Taux de marge par opérateur                │ Barres    │ MART_KPI_OPERATEUR               │ Taux de marge brute par vendeur                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  84 │ % lignes remboursables                     │ Barres    │ MART_KPI_OPERATEUR               │ Part lignes remboursables par opérateur                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  88 │ Productivité CA moyen par jour             │ Barres    │ MART_KPI_OPERATEUR               │ CA moyen par jour et par opérateur                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │  91 │ Heure de pic CA par opérateur              │ Tableau   │ MART_KPI_OPERATEUR               │ Heure avec le plus de CA par vendeur                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D5 - Performance vendeurs      │ 370 │ Nb clients/jour par opérateur              │ Tableau   │ MART_KPI_OPERATEUR               │ Nb moyen de clients par jour et par vendeur                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D6 - Univers RX OTC PARA       │ 357 │ CA par univers                             │ Camembert │ MART_KPI_UNIVERS                 │ CA par univers (RX, OTC, PARA)                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D6 - Univers RX OTC PARA       │ 358 │ Taux de marge par univers                  │ Barres    │ MART_KPI_UNIVERS                 │ Taux de marge brute par univers                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D6 - Univers RX OTC PARA       │ 359 │ Mix CA (% par univers)                     │ Barres    │ MART_KPI_UNIVERS                 │ Répartition du CA en % par univers                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D6 - Univers RX OTC PARA       │ 360 │ Mix marge (% par univers)                  │ Camembert │ MART_KPI_UNIVERS                 │ Répartition de la marge en % par univers                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Ventes & Perf.      │ D6 - Univers RX OTC PARA       │ 361 │ Évolution CA vs A-1 par univers            │ Tableau   │ MART_KPI_UNIVERS                 │ Évolution CA par univers vs année précédente                 │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │  97 │ Rotation stock mensuelle                   │ Courbe    │ MART_KPI_STOCK                   │ Nb rotations du stock par mois                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 100 │ Taux de rupture stock                      │ Courbe    │ MART_KPI_STOCK                   │ % produits en rupture de stock                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 104 │ Valorisation stock PA fin mois             │ Courbe    │ MART_KPI_STOCK_VALORISATION      │ Valeur stock au prix d'achat fin de mois                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 108 │ Couverture stock en jours                  │ Courbe    │ MART_KPI_STOCK_VALORISATION      │ Nb jours de vente couverts par le stock                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 112 │ Marge latente moyenne                      │ Nombre    │ MART_KPI_STOCK_VALORISATION      │ Marge potentielle moyenne sur le stock                       │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 371 │ Stock moyen vs ventes                      │ Barres    │ MART_KPI_STOCK                   │ Comparaison stock moyen et quantités vendues                 │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D7 - Stock et rotation         │ 372 │ Variation prix d'achat                     │ Tableau   │ MART_KPI_STOCK_VALORISATION      │ Évolution prix d'achat (détection inflation)                 │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 117 │ CA estimé perdu par mois                   │ Barres    │ MART_KPI_RUPTURES                │ CA perdu à cause des ruptures                                │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 120 │ Marge estimée perdue                       │ Courbe    │ MART_KPI_RUPTURES                │ Marge perdue à cause des ruptures                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 124 │ Clients impactés par mois                  │ Courbe    │ MART_KPI_RUPTURES                │ Nb clients affectés par les ruptures                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 128 │ Taux de rupture demande                    │ Courbe    │ MART_KPI_RUPTURES                │ % demandes non satisfaites                                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 373 │ Top 10 produits en rupture                 │ Barres    │ MART_KPI_RUPTURES, DIM_PRODUIT   │ Les 10 produits avec le plus de ruptures                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D8 - Ruptures et CA perdu      │ 374 │ Jours de rupture par produit               │ Tableau   │ MART_KPI_RUPTURES, DIM_PRODUIT   │ Nb jours en rupture par produit                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D9 - Écoulement                │ 134 │ Taux d'écoulement mensuel                  │ Courbe    │ MART_KPI_ECOULEMENT              │ Taux d'écoulement global par mois                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D9 - Écoulement                │ 136 │ Commandé vs vendu par mois                 │ Barres    │ MART_KPI_ECOULEMENT              │ Comparaison quantités commandées et vendues                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D9 - Écoulement                │ 140 │ Produits sur-stockés (taux < 50%)          │ Tableau   │ MART_KPI_ECOULEMENT              │ Produits avec écoulement < 50%                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D9 - Écoulement                │ 384 │ Écoulement par fournisseur                 │ Barres    │ MART_KPI_ECOULEMENT, DIM_PRODUIT,│ Taux d'écoulement moyen par fournisseur                      │
│                     │                                │     │                                            │           │ DIM_FOURNISSEUR                  │                                                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D10 - Remises fournisseurs     │ 362 │ Remise pondérée par labo                   │ Barres    │ MART_KPI_REMISE_LABO             │ Remise pondérée par quantités pour chaque labo               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D10 - Remises fournisseurs     │ 363 │ PDM achats par labo                        │ Camembert │ MART_KPI_REMISE_LABO             │ Part de marché en achats par labo                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D10 - Remises fournisseurs     │ 364 │ Remise simple vs pondérée                  │ Tableau   │ MART_KPI_REMISE_LABO             │ Comparaison remise moyenne et pondérée                       │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D10 - Remises fournisseurs     │ 365 │ Évolution remise vs A-1                    │ Tableau   │ MART_KPI_REMISE_LABO             │ Évolution remises vs année précédente par labo               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D10 - Remises fournisseurs     │ 385 │ Montant achats par labo + évolution        │ Tableau   │ MART_KPI_REMISE_LABO             │ Montant total achats et évolution vs A-1                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 147 │ Capital immobilisé (dormants 6m)           │ Nombre    │ MART_KPI_DORMANT                 │ Valeur stock immobilisé dans les dormants                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 151 │ Nb produits dormants 6m                    │ Nombre    │ MART_KPI_DORMANT                 │ Nb produits sans vente depuis 6 mois                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 154 │ Marge latente bloquée                      │ Nombre    │ MART_KPI_DORMANT                 │ Marge immobilisée dans les stocks dormants                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 156 │ Répartition par statut dormant             │ Camembert │ MART_KPI_DORMANT                 │ Ventilation produits par statut de dormance                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 160 │ Dormants par univers                       │ Barres    │ MART_KPI_DORMANT                 │ Répartition des dormants par univers                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 164 │ Top 20 dormants par valeur                 │ Tableau   │ MART_KPI_DORMANT                 │ Les 20 dormants avec la plus grande valeur stock             │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Achats & Stock      │ D11 - Produits dormants        │ 386 │ Dormants par fournisseur                   │ Barres    │ MART_KPI_DORMANT                 │ Nb produits dormants par fournisseur                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 170 │ Répartition A / B / C                      │ Camembert │ MART_KPI_ABC                     │ Nb produits par classe ABC                                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 173 │ CA par classe ABC                          │ Barres    │ MART_KPI_ABC                     │ CA par classe A, B ou C                                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 176 │ Courbe de Pareto (% CA cumulé)             │ Courbe    │ MART_KPI_ABC                     │ Courbe ABC : % CA cumulé par produit                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 180 │ Top 10 produits A                          │ Tableau   │ MART_KPI_ABC                     │ Les 10 premiers produits de la classe A                      │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 387 │ Nb produits classe A                       │ Nombre    │ MART_KPI_ABC                     │ Nombre de produits en classe A                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 400 │ Nb produits classe B                       │ Nombre    │ MART_KPI_ABC                     │ Nombre de produits en classe B                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D12 - Classification ABC       │ 401 │ Nb produits classe C                       │ Nombre    │ MART_KPI_ABC                     │ Nombre de produits en classe C                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 186 │ Taux générique pharmacie                   │ Nombre    │ MART_KPI_GENERIQUE               │ Taux de substitution générique                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 189 │ CA générique vs princeps                   │ Barres    │ MART_KPI_GENERIQUE               │ CA génériques comparé aux princeps                           │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 192 │ PDM par labo (top 15)                      │ Barres    │ MART_KPI_GENERIQUE               │ Part de marché des 15 premiers labos                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 196 │ Nb produits par labo                       │ Barres    │ MART_KPI_GENERIQUE               │ Nb produits référencés par labo                              │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 200 │ Évolution CA par labo vs A-1               │ Tableau   │ MART_KPI_GENERIQUE               │ Évolution CA par labo vs année précédente                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D13 - Génériques et labos      │ 402 │ Marge générique vs princeps                │ Barres    │ MART_KPI_GENERIQUE_MARGE         │ Taux de marge génériques vs princeps                         │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 205 │ Taux pharmacies OK                         │ Nombre    │ MART_KPI_QUALITE_DONNEES         │ % pharmacies avec données à jour                             │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 208 │ Nb erreurs total                           │ Nombre    │ MART_KPI_QUALITE_DONNEES         │ Nb total d'erreurs détectées                                 │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 212 │ Répartition OK / Alerte / Critique         │ Camembert │ MART_KPI_QUALITE_DONNEES         │ Ventilation pharmacies par statut fraîcheur                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 216 │ Fraîcheur par pharmacie                    │ Tableau   │ MART_KPI_QUALITE_DONNEES         │ Statut fraîcheur des données par pharmacie                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 220 │ Erreurs récentes                           │ Tableau   │ MART_KPI_QUALITE_DONNEES         │ Liste des erreurs les plus récentes                          │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Qualité & Pilotage  │ D14 - Qualité des données      │ 403 │ Nb pharmacies en alerte                    │ Nombre    │ MART_KPI_QUALITE_DONNEES         │ Nb pharmacies en statut alerte ou critique                   │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D15 - Détail transactions      │ 227 │ Ventes par jour                            │ Courbe    │ FACT_VENTES                      │ Détail des ventes quotidiennes                               │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D15 - Détail transactions      │ 236 │ Ventes par sexe                            │ Camembert │ FACT_VENTES                      │ Répartition des ventes par sexe client                       │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D15 - Détail transactions      │ 241 │ Commandes par fournisseur                  │ Barres    │ FACT_COMMANDES                   │ Volume de commandes par fournisseur                          │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D15 - Détail transactions      │ 404 │ Top produits vendus                        │ Barres    │ MART_KPI_VENTES_PAR_PRODUIT      │ Les produits les plus vendus en quantité                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D15 - Détail transactions      │ 405 │ CA par tranche d'âge                       │ Barres    │ FACT_VENTES                      │ CA par tranche d'âge client                                  │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D16 - Prix et mouvements stock │ 249 │ Évolution prix (tarif, public, achat net)  │ Courbe    │ FACT_PRIX_JOURNALIER             │ Évolution des 3 prix d'un produit                            │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D16 - Prix et mouvements stock │ 251 │ Marge brute unitaire                       │ Courbe    │ FACT_PRIX_JOURNALIER             │ Évolution de la marge brute par unité                        │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D16 - Prix et mouvements stock │ 256 │ Mouvements stock par jour                  │ Barres    │ FACT_STOCK_MOUVEMENT             │ Entrées et sorties de stock quotidiennes                     │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D16 - Prix et mouvements stock │ 261 │ Type opération stock                       │ Camembert │ FACT_STOCK_MOUVEMENT             │ Répartition par type d'opération de stock                    │
├─────────────────────┼────────────────────────────────┼─────┼────────────────────────────────────────────┼───────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ Détail opérationnel │ D16 - Prix et mouvements stock │ 406 │ Niveau stock après mouvement               │ Courbe    │ FACT_STOCK_MOUVEMENT             │ Niveau de stock après chaque mouvement                       │
└─────────────────────┴────────────────────────────────┴─────┴────────────────────────────────────────────┴───────────┴──────────────────────────────────┴──────────────────────────────────────────────────────────────┘

**Total** : 5 collections, 16 dashboards, 98 cards, 28/32 tables MARTS utilisées.

> 4 tables non utilisées directement : 
┌─────────────────────────┬───────────────────────────────────────────┐
│          Table          │                  Raison                   │
├─────────────────────────┼───────────────────────────────────────────┤
│                         │ Utilisée indirectement via le filtre      │
│ DIM_PHARMACIE           │ Pharmacie (PHARMACIE_SK), mais aucune     │
│                         │ card ne la requête directement            │
├─────────────────────────┼───────────────────────────────────────────┤
│ FACT_OPERATEUR          │ Redondant avec MART_KPI_OPERATEUR qui     │
│                         │ agrège déjà les données opérateur         │
├─────────────────────────┼───────────────────────────────────────────┤
│ FACT_RUPTURES           │ Redondant avec MART_KPI_RUPTURES qui      │
│                         │ agrège déjà les ruptures                  │
├─────────────────────────┼───────────────────────────────────────────┤
│                         │ Redondant avec                            │
│ FACT_STOCK_VALORISATION │ MART_KPI_STOCK_VALORISATION qui agrège    │
│                         │ déjà les valorisations                    │
└─────────────────────────┴───────────────────────────────────────────┘
C'est normal : les tables FACT_* contiennent les données granulaires
(ligne par ligne), tandis que les MART_KPI_* contiennent les agrégations
prêtes pour la BI. Les dashboards utilisent les KPIs pré-calculés, pas
les faits bruts. Les FACT restent disponibles pour du drill-down ad hoc
si besoin.

[↑ Retour au sommaire](#table-des-matières)

---

## 7. Couverture des 32 tables MARTS

┌─────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
│ Table MARTS                         │ Dashboard(s)                         │ Statut                                                   │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ DIM_PHARMACIE                       │ Tous (filtre indirect PHARMACIE_SK)  │ indirect                                                 │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ DIM_PRODUIT                         │ D4, D8, D9                           │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ DIM_FOURNISSEUR                     │ D9                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_VENTES                         │ D15                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_COMMANDES                      │ D15                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_TRESORERIE                     │ D3                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_PRIX_JOURNALIER                │ D16                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_STOCK_MOUVEMENT                │ D16                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_OPERATEUR                      │ —                                    │ non utilisée (redondant avec MART_KPI_OPERATEUR)         │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_RUPTURES                       │ —                                    │ non utilisée (redondant avec MART_KPI_RUPTURES)          │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ FACT_STOCK_VALORISATION             │ —                                    │ non utilisée (redondant avec MART_KPI_STOCK_VALORISATION)│
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_SYNTHESE_PHARMACIE         │ D1                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_CA_EVOLUTION               │ D2                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_TRESORERIE                 │ D3                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_MARGE                      │ D4                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_MARGE_PAR_PRODUIT          │ D4                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_MARGE_PAR_UNIVERS          │ D4                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_OPERATEUR                  │ D5                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_UNIVERS                    │ D6                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_STOCK                      │ D7                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_STOCK_VALORISATION         │ D7                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_RUPTURES                   │ D8                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_RUPTURES_PAR_PRODUIT       │ D8                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_ECOULEMENT                 │ D9                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_ECOULEMENT_PAR_FOURNISSEUR │ D9                                   │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_REMISE_LABO                │ D10                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_DORMANT                    │ D11                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_ABC                        │ D12                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_GENERIQUE                  │ D13                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_GENERIQUE_MARGE            │ D13                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_QUALITE_DONNEES            │ D14                                  │ ✓ utilisée                                               │
├─────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MART_KPI_VENTES_PAR_PRODUIT         │ D15                                  │ ✓ utilisée                                               │
└─────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────────────────────┘

**28/32 tables utilisées directement.** 4 tables non utilisées : `DIM_PHARMACIE` (filtre indirect), `FACT_OPERATEUR`, `FACT_RUPTURES`, `FACT_STOCK_VALORISATION` (redondantes avec les MART_KPI pré-agrégés).

[↑ Retour au sommaire](#table-des-matières)

---

## 8. Conseils pratiques

### Types de visualisation Metabase

┌────────────────────┬───────────────────────────────────────────────────────────────┐
│ Type               │ Quand l'utiliser                                              │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Nombre (scalar)    │ Un chiffre clé unique (CA total, nb produits, somme…)         │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Courbe (line)      │ Évolution dans le temps (CA par mois, tendance…)              │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Barres (bar)       │ Comparaison entre catégories (CA par univers, par labo…)      │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Camembert (pie)    │ Répartition en pourcentages (mix CA, statuts…)                │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Tableau (table)    │ Détail ligne par ligne (top produits, liste filtrée…)         │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Aire (area)        │ Évolution cumulée (CA YTD, stock cumulé…)                     │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Jauge (gauge)      │ Valeur vs objectif (taux générique vs 80% CPAM…)              │
├────────────────────┼───────────────────────────────────────────────────────────────┤
│ Heatmap            │ Croisement deux dimensions (produit × mois…)                  │
└────────────────────┴───────────────────────────────────────────────────────────────┘

### Actions fréquentes dans l'éditeur de questions

- **Résumer** (Σ) : agrégation (somme, comptage, moyenne, min, max)
- **Regrouper par** : équivalent du GROUP BY SQL
- **Filtrer** : conditions WHERE
- **Trier** : ORDER BY
- **Limite** : LIMIT (nombre de lignes retournées)
- **Colonnes** : sélection des champs affichés (pour les tableaux)
- **Expression personnalisée** : formules calculées (ex. `[VALEUR_STOCK_PV] - [VALEUR_STOCK_PA]`)

### Raccourcis utiles

- **Mode édition** du dashboard : cliquer sur le crayon (✏️) en haut à droite
- **Sauvegarder** : cliquer sur « Enregistrer » en haut à droite en mode édition
- **Plein écran** : cliquer sur l'icône d'expansion pour une présentation
- **Rafraîchir** : icône horloge > choisir la fréquence de rafraîchissement auto

[↑ Retour au sommaire](#table-des-matières)

---

