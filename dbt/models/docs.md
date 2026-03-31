{% docs __overview__ %}

# MediCore — Data Catalog

Pipeline ELT industrialisé pour un groupement de pharmacies.

## Architecture données

```
MySQL RDS (winstat) → Kafka CDC → Snowflake RAW → dbt STAGING → dbt MARTS → Metabase
```

### Couches

| Couche | Schéma | Contenu |
|--------|--------|---------|
| **RAW** | `RAW` | Copie brute des 18 tables MySQL + métadonnées CDC |
| **STAGING** | `STAGING` | Déduplication CDC + masquage PII + typage |
| **MARTS** | `MARTS` | Star schema : 3 dimensions + 8 faits + 21 KPIs |
| **AUDIT** | `AUDIT` | Lineage opérationnel (runs, steps, modèles dbt) |
| **SNAPSHOTS** | `SNAPSHOTS` | Historisation SCD2 des dimensions |

### Sources de données

| Source | Tables | Mode d'ingestion | Fréquence |
|--------|--------|-------------------|-----------|
| CDC (Kafka/Debezium) | COMMANDES, FACTURES, ORDERS, MODSTOCK | Micro-batch 500 events | Toutes les 10 min |
| Référence (bulk load) | 14 tables (DAYBYDAY, PRODUITS, FOURNISSEURS...) | MySQL → Parquet → COPY INTO | 1x/jour à 01h |

### Environnements

| Environnement | Database | Usage |
|---------------|----------|-------|
| Production | `MEDICORE_PROD` | Données réelles, dashboards Metabase |
| Développement | `MEDICORE_DEV` | Clone zero-copy de PROD |
| Test (CI) | `MEDICORE_TEST` | Seeds CSV, GitHub Actions |

{% enddocs %}


{% docs _pharmacie %}
## Pharmacie

Entité centrale du modèle. Chaque pharmacie du groupement est identifiée par un `PHA_ID` unique
(source MySQL winstat). La dimension `dim_pharmacie` attribue une surrogate key `pharmacie_sk`
utilisée comme FK dans toutes les tables de faits.

Le nom de la pharmacie (`PHA_NOM`) est la raison sociale de l'entreprise (pas une donnée personnelle).

{% enddocs %}


{% docs _produit %}
## Produit

Un produit pharmaceutique identifié par `PRD_ID` (source MySQL winstat). La dimension `dim_produit`
enrichit le produit avec :

- **EAN13** : code-barres 13 chiffres (table `stg_ean13`)
- **LPP** : code Liste des Produits et Prestations Remboursables (table `stg_lppr`)
- **Univers** : classification basée sur le code de remboursement :
  - **RX** : médicaments sur ordonnance (remboursables)
  - **OTC** : médicaments conseil (sans ordonnance)
  - **PARA** : parapharmacie
  - **HORS_REMB** : produits hors remboursement
- **Générique** : identifié par `PRD_REFGEN` (codes 71, 82)
- **Dernière vente** : date de la dernière transaction (détection produits dormants)

{% enddocs %}


{% docs _fournisseur %}
## Fournisseur

Laboratoire pharmaceutique ou grossiste-répartiteur identifié par `FOU_ID`.
La dimension `dim_fournisseur` attribue une surrogate key `fournisseur_sk`.

Types de fournisseurs :
- **Grossiste-répartiteur** : distributeur intermédiaire (OCP, Alliance, CERP)
- **Laboratoire** : fabricant du médicament (Sanofi, Pfizer, Teva...)
- **Direct** : livraison directe laboratoire → pharmacie

{% enddocs %}


{% docs _star_schema %}
## Star Schema

Le modèle dimensionnel MARTS suit un star schema classique :

```
                    dim_pharmacie
                         │
                         │ pharmacie_sk
                         │
dim_fournisseur ────── FAITS ────── dim_produit
                    (8 tables)
         fournisseur_sk      produit_sk
```

### Dimensions

| Dimension | Clé surrogate | Clé métier | Source |
|-----------|---------------|------------|--------|
| dim_pharmacie | pharmacie_sk | PHA_ID | stg_pharmacie |
| dim_produit | produit_sk | PRD_ID | stg_produits + stg_ean13 + stg_lppr |
| dim_fournisseur | fournisseur_sk | FOU_ID | stg_fournisseurs |

### Gestion des orphelins

Les faits utilisent `COALESCE(dim.sk, -1)` pour les FK manquantes.
Un produit ou une pharmacie non trouvé dans la dimension reçoit la SK `-1`
au lieu de NULL, ce qui évite les pertes de lignes lors des LEFT JOIN.

{% enddocs %}


{% docs _marge %}
## Marge

La marge brute est calculée dans `mart_kpi_marge` :

```
marge_brute = CA_HT - (quantité_vendue × prix_achat_moyen_pondéré)
taux_marge  = marge_brute / CA_HT
```

- **CA_HT** : chiffre d'affaires hors taxes (source: `fact_ventes`)
- **PAMP** : Prix d'Achat Moyen Pondéré (source: `fact_prix_journalier`)
- Le taux de marge est NULL si CA_HT = 0 (division par zéro évitée)
- La marge peut être **négative** (vente à perte, promotions)

### Marge par univers

`mart_kpi_marge_par_univers` agrège la marge par classification produit (RX, OTC, PARA).
Les marges typiques en pharmacie :
- RX (ordonnance) : 20-25%
- OTC (conseil) : 25-35%
- PARA (parapharmacie) : 30-45%

{% enddocs %}


{% docs _ecoulement %}
## Taux d'écoulement (sell-through)

Mesure la performance d'écoulement des achats. Calculé dans `mart_kpi_ecoulement` :

```
taux_écoulement = quantité_vendue / quantité_commandée
```

- **> 1.0** : ventes supérieures aux achats (déstockage)
- **= 1.0** : équilibre parfait achats/ventes
- **< 1.0** : accumulation de stock
- **NULL** : aucune commande dans la période

Un taux d'écoulement faible sur plusieurs mois signale un risque de stock dormant.

{% enddocs %}


{% docs _abc %}
## Classification ABC (Pareto)

Classement des produits par contribution au CA, calculé dans `mart_kpi_abc` :

```
Classe A : produits représentant 80% du CA cumulé (top performers)
Classe B : produits entre 80% et 95% du CA cumulé (contributeurs moyens)
Classe C : produits au-delà de 95% du CA cumulé (longue traîne)
```

En pharmacie, typiquement :
- **Classe A** : 15-20% des références = 80% du CA
- **Classe B** : 20-30% des références = 15% du CA
- **Classe C** : 50-65% des références = 5% du CA

Les produits de classe C sont des candidats au désréférencement si leur stock est élevé.

{% enddocs %}


{% docs _ruptures %}
## Ruptures de stock

Une rupture est une demande client non satisfaite (source: table `MANQHISTORY`).

### Deux mesures de rupture

- **Taux de rupture demande** (`mart_kpi_ruptures`) : lignes non satisfaites / total lignes.
  C'est la vue **client** : combien de demandes n'ont pas été servies.

- **Taux de rupture stock** (`mart_kpi_stock`) : jours à stock zéro / jours avec mouvement.
  C'est la vue **stock** : combien de jours le produit était indisponible.

### CA estimé perdu

```
ca_estimé_perdu = boîtes_manquantes × prix_public_moyen_du_mois
marge_estimée_perdue = boîtes_manquantes × (prix_public - prix_achat)_moyen
```

Ces estimations permettent de prioriser les actions de réapprovisionnement.

{% enddocs %}


{% docs _stock_valorisation %}
## Valorisation du stock

Le stock est valorisé quotidiennement dans `fact_stock_valorisation` :

```
valeur_stock_PA = quantité_en_stock × prix_achat_moyen_pondéré
valeur_stock_PV = quantité_en_stock × prix_public
marge_latente   = valeur_PV - valeur_PA (marge en rayon non réalisée)
```

### Couverture de stock

```
couverture_jours = (stock_fin_mois × 30) / quantité_vendue_mois
```

- **< 15 jours** : risque de rupture
- **15-45 jours** : couverture optimale
- **> 90 jours** : surstock, capital immobilisé

### Stock dormant

Un produit est considéré **dormant** si son stock est > 0 mais aucune vente n'est
enregistrée depuis 6 mois (`is_dormant_6m`) ou 12 mois (`is_dormant_12m`).

{% enddocs %}


{% docs _tresorerie %}
## Trésorerie

La trésorerie journalière (`fact_tresorerie`) ventile les encaissements par mode de paiement :

| Mode | Description |
|------|-------------|
| Espèces (EUR) | Paiements cash au comptoir |
| CB | Carte bancaire |
| Chèques (EUR) | Chèques bancaires |
| Mutuelles | Tiers payant complémentaire |
| Virements | Virements bancaires |
| Subrogation | Part assurée (tiers payant obligatoire) |

### Panier moyen

```
panier_moyen = CA_total / nombre_de_factures
```

### Part tiers payant

```
pct_tiers_payant = (mutuelle + centre + subrogation) / CA_total
```

Un taux de tiers payant élevé (> 70%) indique une pharmacie orientée ordonnance (RX).

{% enddocs %}


{% docs _operateur %}
## Performance opérateur

Un opérateur est un vendeur en pharmacie identifié par son nom (`ORD_OPERATEUR`).
Les KPIs opérateur (`mart_kpi_operateur`) mesurent :

- **CA mensuel** : chiffre d'affaires HT et TTC
- **Panier moyen** : CA / nombre de lignes
- **Taux de marge** : (CA HT - coût achat) / CA HT
- **Clients/jour** : nombre moyen de clients distincts servis par jour
- **Heure de pic** : heure avec le plus de CA (gestion des plannings)
- **Mix remboursable** : part des ventes sur ordonnance vs conseil libre

{% enddocs %}


{% docs _pii_masking %}
## Masquage PII

Les données personnelles identifiantes (PII) sont masquées dans la couche STAGING
via la macro `pii_mask()` (hash MD5).

### Colonnes masquées

| Colonne | Table | Raison du masquage |
|---------|-------|--------------------|
| FOU_ADRESSE | stg_fournisseurs | Adresse postale (seule PII restante) |

### Colonnes démasquées (raisons métier)

| Colonne | Table | Raison |
|---------|-------|--------|
| PHA_NOM | stg_pharmacie | Raison sociale (entreprise, pas PII) |
| FOU_NOM | stg_fournisseurs | Nom de laboratoire (entreprise) |
| ORD_OPERATEUR | stg_orders | Nécessaire pour le dashboard D5 Performance vendeurs |

Le masquage est appliqué **uniquement en staging**. Les données RAW restent en clair
(principe ELT : pas de transformation avant le DWH).

{% enddocs %}


{% docs _cdc %}
## CDC (Change Data Capture)

4 tables sont alimentées en temps quasi-réel via Debezium/Kafka :

| Table | Contenu | Volume |
|-------|---------|--------|
| COMMANDES | Commandes fournisseurs | ~41M lignes |
| FACTURES | Factures de vente | ~189M lignes |
| ORDERS | Ordonnances | ~60M lignes |
| MODSTOCK | Mouvements de stock | ~181M lignes |

### Opérations CDC Debezium

| Code | Opération | Mapping |
|------|-----------|---------|
| `c` | Create (INSERT) | `I` |
| `u` | Update | `U` |
| `d` | Delete | `D` |
| `r` | Read (snapshot initial) | `I` |

### Déduplication staging

Les modèles staging dédupliquent via :
```sql
ROW_NUMBER() OVER (PARTITION BY PK ORDER BY CDC_TIMESTAMP DESC) = 1
```
Et filtrent les deletes : `WHERE CDC_OPERATION != 'D'`

{% enddocs %}
