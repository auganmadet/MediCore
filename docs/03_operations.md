# Guide opérationnel MediCore

## Table des matières

1. [Démarrage](#démarrage)
2. [Architecture du batch](#architecture-du-batch)
3. [Lineage opérationnel (AUDIT)](#lineage-opérationnel-audit)
4. [Monitoring et alertes](#monitoring-et-alertes)
5. [Diagnostic et recovery](#diagnostic-et-recovery)
6. [Variables d'environnement](#variables-denvironnement)
7. [Commandes utiles](#commandes-utiles)
8. [Arrêt propre](#arrêt-propre)
9. [Data Catalog (dbt docs)](#data-catalog-dbt-docs)
   - [Accès](#accès-data-catalog)
   - [Régénérer le catalogue](#régénérer-le-catalogue)
   - [Pare-feu Windows](#pare-feu-windows)
10. [Metabase (BI dashboards)](#metabase-bi-dashboards)
    - [Architecture](#architecture)
    - [Accès](#accès)
    - [Configuration Snowflake](#configuration-snowflake-premier-lancement)
    - [Ressources ajoutées](#ressources-ajoutées)
    - [Variables d'environnement Metabase](#variables-denvironnement-1)
    - [Vérification](#vérification)
    - [Plan dashboards](#plan-dashboards--16-dashboards-2626-tables-95-cartes)

---

## Démarrage

```bash
# Premier lancement (DDL + Docker + Debezium connector)
./scripts/setup.sh

# Lancement quotidien
docker compose up -d
```

[↑ Retour au sommaire](#table-des-matières)

## Architecture du batch

Le conteneur `medicore_elt_batch` exécute `batch_loop.sh` en boucle (5 min dev / 30 min prod).

Chaque itération :

  ┌───────┬──────────────────────────────────────────────────────┐
  │ Phase │ Description                                          │
  ├───────┼──────────────────────────────────────────────────────┤
  │   0   │ Re-bulk référence (14 tables, 1x/jour à 01h)         │
  ├───────┼──────────────────────────────────────────────────────┤
  │   1   │ CDC Kafka -> Snowflake RAW (4 tables)                │
  ├───────┼──────────────────────────────────────────────────────┤
  │   2   │ dbt run staging (dédup + PII masking)                │
  ├───────┼──────────────────────────────────────────────────────┤
  │   3   │ dbt snapshot (SCD2)                                  │
  ├───────┼──────────────────────────────────────────────────────┤
  │   4a  │ dbt run marts (dimensions + faits + KPIs)            │
  ├───────┼──────────────────────────────────────────────────────┤
  │   4b  │ dbt test staging + marts                             │
  ├───────┼──────────────────────────────────────────────────────┤
  │   5   │ dbt source freshness                                 │
  └───────┴──────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

## Lineage opérationnel (AUDIT)

Chaque itération génère un `RUN_ID` UUID. Les résultats sont persistés dans `MEDICORE_PROD.AUDIT` :

```sql
-- Derniers runs
SELECT * FROM MEDICORE_PROD.AUDIT.PIPELINE_RUNS ORDER BY RUN_START DESC LIMIT 10;

-- Détail des étapes d'un run
SELECT * FROM MEDICORE_PROD.AUDIT.PIPELINE_STEP_RUNS WHERE RUN_ID = '<uuid>' ORDER BY STEP_START;

-- Résultats dbt par run
SELECT * FROM MEDICORE_PROD.AUDIT.DBT_MODEL_RUNS WHERE RUN_ID = '<uuid>';

-- Vue résumé
SELECT * FROM MEDICORE_PROD.AUDIT.AUDIT_RUN_SUMMARY ORDER BY RUN_START DESC LIMIT 10;

-- Lag Kafka par topic (derniers runs)
SELECT * FROM MEDICORE_PROD.AUDIT.CDC_LAG_METRICS ORDER BY CREATED_AT DESC LIMIT 20;

-- Statistiques lag pour calibrer le seuil
SELECT AVG(LAG), MAX(LAG), PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY LAG)
FROM MEDICORE_PROD.AUDIT.CDC_LAG_METRICS;
```

Rétention automatique : 90 jours (purge quotidienne à 00h).

[↑ Retour au sommaire](#table-des-matières)

## Monitoring et alertes

  ┌───────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Mécanisme                 │ Configuration                                            │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Teams webhook             │ `TEAMS_WEBHOOK_URL` (.env)                               │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Seuil alerte              │ `ALERT_THRESHOLD` (défaut: 3)                            │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Freshness CDC             │ warn 12h / error 24h                                     │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Freshness référence       │ warn 36h / error 48h                                     │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Volume CDC                │ Alerte après N batches à 0 events                        │
  ├───────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Lag Kafka                 │ Alerte si lag > `KAFKA_LAG_THRESHOLD` N fois consécutives │
  └───────────────────────────┴──────────────────────────────────────────────────────────┘

Le **lag Kafka** mesure le retard du consumer CDC (end_offset - committed_offset). Un lag croissant signifie que le consumer ne suit pas le rythme de Debezium. Les métriques sont écrites dans `/tmp/cdc_lag_metrics` et historisées dans `AUDIT.CDC_LAG_METRICS`.

[↑ Retour au sommaire](#table-des-matières)

## Diagnostic et recovery

```bash
# Diagnostic seul (lecture seule)
docker exec medicore_elt_batch python pipelines/diagnose_recover.py

# Diagnostic + correction automatique
docker exec medicore_elt_batch python pipelines/diagnose_recover.py --fix
```

Détecte : processus zombies, tables vides, doublons, timestamps invalides.

[↑ Retour au sommaire](#table-des-matières)

## Variables d'environnement

  ┌──────────────────────────────┬────────────────────────────────────────────┐
  │ Variable                     │ Description                                │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `ENV`                        │ Environnement (dev/prod)                   │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_ACCOUNT`          │ Compte Snowflake                           │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_USER`             │ Utilisateur Snowflake                      │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_PASSWORD`         │ Mot de passe Snowflake                     │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_DATABASE`         │ Base de données (défaut: MEDICORE_PROD)    │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `SNOWFLAKE_WAREHOUSE_NAME`   │ Warehouse (défaut: MEDICORE_WH)            │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `BATCH_INTERVAL_MIN`         │ Intervalle batch en minutes                │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `PHASE_TIMEOUT_SEC`          │ Timeout par phase (défaut: 1800)           │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `CDC_BATCH_TIMEOUT_SEC`      │ Timeout consumer Kafka (défaut: 30)        │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `TEAMS_WEBHOOK_URL`          │ Webhook Teams (optionnel)                  │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `ALERT_THRESHOLD`            │ Échecs avant alerte (défaut: 3)            │
  ├──────────────────────────────┼────────────────────────────────────────────┤
  │ `KAFKA_LAG_THRESHOLD`        │ Seuil lag Kafka en records (défaut: 10000) │
  └──────────────────────────────┴────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

## Commandes utiles

```bash
# Shell dans le conteneur
docker exec -it medicore_elt_batch bash

# Logs en temps réel
docker logs -f medicore_elt_batch

# Bulk load manuel (toutes les tables)
docker exec medicore_elt_batch python pipelines/bulk_load.py --truncate

# Bulk load reference uniquement
docker exec medicore_elt_batch python pipelines/bulk_load.py --ref-only --truncate

# Consumer CDC manuel
docker exec medicore_elt_batch python pipelines/daily_cdc_batch.py

# dbt commands
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt run --select tag:staging"
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt test --select stg_*"
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt source freshness"

# Kafdrop (UI Kafka)
# http://localhost:9000
```

[↑ Retour au sommaire](#table-des-matières)

## Arrêt propre

```bash
# Arrêt graceful (attend la fin de la phase en cours)
docker compose stop medicore-elt-batch

# Arrêt complet
docker compose down
```

Le conteneur intercepte SIGTERM et termine proprement après la phase en cours.

[↑ Retour au sommaire](#table-des-matières)

## Data Catalog (dbt docs)

Catalogue de données interactif généré par dbt, accessible sur le réseau local comme Metabase.
Permet de naviguer les modèles, colonnes, tests et le lineage visuel (source → staging → marts).

### Accès Data Catalog

  ┌─────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Accès                           │ URL                                                      │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Local (machine Docker)          │ http://localhost:8080                                    │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ Réseau local                    │ http://192.168.0.37:8080                                 │
  └─────────────────────────────────┴──────────────────────────────────────────────────────────┘

Le service `dbt_docs` est un serveur HTTP léger (Python, 128 Mo) qui sert les fichiers
générés dans `dbt/target/` (index.html, catalog.json, manifest.json).

### Régénérer le catalogue

Après modification des modèles ou des descriptions YAML, régénérer le catalogue :

```bash
docker exec medicore_elt_batch bash -c "cd /app/dbt && dbt docs generate --target prod"
```

Le service `dbt_docs` sert le contenu de `dbt/target/` en lecture seule — la mise à jour
est immédiate après régénération (pas besoin de redémarrer le service).

### Pare-feu Windows

Pour rendre le Data Catalog accessible depuis le réseau local, ouvrir le port 8080
dans le pare-feu Windows (à exécuter une seule fois, en administrateur) :

```cmd
netsh advfirewall firewall add rule name="dbt-docs" dir=in action=allow protocol=TCP localport=8080
```

Sans cette règle, seul `http://localhost:8080` fonctionne (pas l'IP réseau).

  ┌───────────────────────────┬──────────┬─────────────────────────────────────────────────────┐
  │ Service                   │ Port     │ Pare-feu Windows                                    │
  ├───────────────────────────┼──────────┼─────────────────────────────────────────────────────┤
  │ Metabase (BI dashboards)  │ 3000     │ netsh ... name="Metabase" localport=3000            │
  ├───────────────────────────┼──────────┼─────────────────────────────────────────────────────┤
  │ Data Catalog (dbt docs)   │ 8080     │ netsh ... name="dbt-docs" localport=8080            │
  ├───────────────────────────┼──────────┼─────────────────────────────────────────────────────┤
  │ Kafdrop (Kafka UI)        │ 9000     │ Pas exposé réseau (127.0.0.1 uniquement)            │
  └───────────────────────────┴──────────┴─────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

## Metabase (BI dashboards)

Metabase est une application BI open-source qui se connecte en lecture seule à Snowflake MARTS pour visualiser les 21 KPIs, 8 faits et 3 dimensions sur des dashboards interactifs.

### Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Navigateur web │────>│  Metabase (Java)     │────>│  Snowflake MARTS    │
│  localhost:3000 │     │  conteneur Docker    │     │  lecture seule      │
└─────────────────┘     │                      │     │  21 KPIs + 8 facts  │
                        │  Metadata stockée    │     │  + 3 dimensions     │
                        │  dans PostgreSQL     │     └─────────────────────┘
                        └──────────────────────┘
```

Metabase ne stocke aucune donnée métier — il fait des `SELECT` sur Snowflake à chaque requête. PostgreSQL stocke uniquement la config Metabase (dashboards, questions, comptes utilisateurs).

### Acces

```
http://localhost:3000
```

### Configuration Snowflake (premier lancement)

Au premier lancement, Metabase affiche un wizard de configuration :

1. Créer un compte admin Metabase
2. Ajouter la base de données Snowflake :

  ┌──────────────────┬────────────────────────────────────┐
  │ Paramètre        │ Valeur                             │
  ├──────────────────┼────────────────────────────────────┤
  │ Type             │ Snowflake                          │
  ├──────────────────┼────────────────────────────────────┤
  │ Account          │ `SNOWFLAKE_ACCOUNT` (.env)         │
  ├──────────────────┼────────────────────────────────────┤
  │ User             │ Utilisateur avec role ANALYST      │
  ├──────────────────┼────────────────────────────────────┤
  │ Password         │ Mot de passe de l'utilisateur      │
  ├──────────────────┼────────────────────────────────────┤
  │ Database         │ MEDICORE_PROD                      │
  ├──────────────────┼────────────────────────────────────┤
  │ Schema           │ MARTS                              │
  ├──────────────────┼────────────────────────────────────┤
  │ Warehouse        │ MEDICORE_WH                        │
  ├──────────────────┼────────────────────────────────────┤
  │ Role             │ MEDICORE_ANALYST                   │
  └──────────────────┴────────────────────────────────────┘

3. Metabase scanne automatiquement les 26 tables MARTS

**Note** : le rôle `MEDICORE_ANALYST` et ses grants sont créés par `scripts/DDL_TABLES.sql`. L'assignation du rôle à un utilisateur reste manuelle :

```sql
GRANT ROLE MEDICORE_ANALYST TO USER <nom_utilisateur>;
```

### Ressources ajoutées

  ┌──────────────────┬────────┬────────┬──────────────────────────┐
  │ Service          │ RAM    │ CPU    │ Rôle                     │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ Metabase (Java)  │ 2 GB   │ 1 core │ Application BI           │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ PostgreSQL 16    │ 512 MB │ 0.5    │ Metadata Metabase        │
  ├──────────────────┼────────┼────────┼──────────────────────────┤
  │ Total ajouté     │ 2.5 GB │ 1.5    │                          │
  └──────────────────┴────────┴────────┴──────────────────────────┘

### Variables d'environnement

  ┌──────────────────────────┬──────────────────────────────────────┐
  │ Variable                 │ Description                          │
  ├──────────────────────────┼──────────────────────────────────────┤
  │ `METABASE_DB_PASSWORD`   │ Mot de passe PostgreSQL Metabase     │
  │                          │ (défaut: metabase_dev)               │
  └──────────────────────────┴──────────────────────────────────────┘

### Vérification

```bash
# Vérifier que les conteneurs tournent
docker ps | grep metabase

# Vérifier la connexion Snowflake dans Metabase
# Admin > Databases > MEDICORE_PROD > Sync status = "done"
```

### Plan dashboards — 16 dashboards, 26/26 tables, 95 cartes

Les dashboards sont organisés en 5 collections Metabase (dossiers avec permissions) :

```
MediCore BI
├── Direction Generale          D1, D2, D3
├── Ventes & Performance        D4, D5, D6
├── Achats & Stock              D7, D8, D9, D10, D11
├── Qualite & Pilotage          D12, D13, D14
└── Detail operationnel         D15, D16
```

#### Tableau recapitulatif

  ┌─────┬─────────────────────────┬──────────────────────┬─────────────────────────────┬────────┬────────────────────────────────────┐
  │  #  │ Dashboard               │ Collection           │ Tables sources              │ Cartes │ Décision stratégique               │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  1  │ Synthèse pharmacie      │ Direction Générale   │ mart_kpi_synthese_pharmacie │   9    │  Ma pharmacie va-t-elle dans       │
  │     │                         │                      │                             │        │  la bonne direction ?              │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  2  │ Évolution CA            │ Direction Générale   │ mart_kpi_ca_evolution       │   5    │  Mon CA progresse-t-il ou          │
  │     │                         │                      │                             │        │  régresse-t-il vs A-1 ?            │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  3  │ Trésorerie              │ Direction Générale   │ mart_kpi_tresorerie +       │   9    │ Comment rentre l'argent et         │
  │     │                         │                      │ fact_tresorerie             │        │ où part-il ?                       │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  4  │ Marge détaillée         │ Ventes & Performance │ mart_kpi_marge + dim_produit│   5    │  Sur quels produits je gagne       │
  │     │                         │                      │ dim_pharma                  │        │  ou perds de l'argent ?            │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  5  │ Performance vendeurs    │ Ventes & Performance │ mart_kpi_operateur          │   7    │  Mes équipes sont-elles            │
  │     │                         │                      │                             │        │  performantes et équilibrées ?     │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  6  │ Univers RX/OTC/PARA     │ Ventes & Performance │ mart_kpi_univers            │   5    │  Mon mix produit est-il équilibré  │
  │     │                         │                      │                             │        │  et rentable ?                     │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  7  │ Stock & rotation        │ Achats & Stock       │ mart_kpi_stock              │   7    │  Mon stock est-il correctement     │
  │     │                         │                      │ stock_valorisation + dim    │        │  dimensionné ?                     │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  8  │ Ruptures & CA perdu     │ Achats & Stock       │ mart_kpi_ruptures           │   6    │  Combien me coûtent les ruptures   │
  │     │                         │                      │ dim_produit                 │        │  de stock ?                        │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │  9  │ Écoulement              │ Achats & Stock       │ mart_kpi_ecoulement +       │   4    │  Ce que j'achète, est-ce que       │
  │     │                         │                      │ dim_produit + dim_f         │        │  ça se vend ?                      │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 10  │ Remises fournisseurs    │ Achats & Stock       │ mart_kpi_remise_labo +      │   4    │  Mes fournisseurs me font-ils      │
  │     │                         │                      │ dim_fournisseur             │        │  de bonnes conditions ?            │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 11  │ Produits dormants       │ Achats & Stock       │ mart_kpi_dormant +          │   7    │  Combien de capital dort dans      │
  │     │                         │                      │ dim_fournisseur             │        │  mes étagères ?                    │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 12  │ Classification ABC      │ Qualité & Pilotage   │ mart_kpi_abc + dim_produit  │   5    │   20% de mes produits font-ils     │
  │     │                         │                      │                             │        │   80% de mon CA ?                  │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 13  │ Génériques & labos      │ Qualité & Pilotage   │ mart_kpi_generique +        │   6    │   Suis-je conforme à l'objectif    │
  │     │                         │                      │ dim_fournisseur             │        │   CPAM 80% ?                       │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 14  │ Qualité des données     │ Qualité & Pilotage   │ mart_kpi_qualite_donnees    │   6    │   Puis-je faire confiance aux      │
  │     │                         │                      │                             │        │   chiffres affichés ?              │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 15  │ Détail transactions     │ Détail opérationnel  │ fact_ventes +               │   5    │  Drill-down sur les transactions   │
  │     │                         │                      │ fact_commandes + dims       │        │  individuelles                     │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │ 16  │ Prix & mouvements stock │ Détail opérationnel  │ fact_prix_journalier +      │   5    │  Comment évoluent mes prix d'achat │
  │     │                         │                      │ fact_stock_mouv.            │        │  et mon stock physique ?           │
  ├─────┼─────────────────────────┼──────────────────────┼─────────────────────────────┼────────┼────────────────────────────────────┤
  │     │ TOTAL                   │ 5 collections        │ 26/26 tables couvertes      │   95   │                                    │
  └─────┴─────────────────────────┴──────────────────────┴─────────────────────────────┴────────┴────────────────────────────────────┘


#### D1 — Synthese pharmacie

**Collection** : Direction Generale | **Table** : `mart_kpi_synthese_pharmacie` | **Filtres** : pharmacie, mois

Le titulaire ouvre ce dashboard chaque matin. En 30 secondes, il sait si sa pharmacie va bien ou non. C'est le tableau de bord du cockpit — tous les voyants au vert = rien a faire, un voyant rouge = creuser.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA mensuel + evolution                 │ `ca_ht`, `ca_ht_a1`, `evolution_ca_vs_a1` (nombre+tendance)  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA YTD vs A-1                          │ `ca_ht_ytd`, `ca_ht_ytd_a1`, `evolution_ytd_vs_a1` (nombre)  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA 12DM glissants                      │ `ca_ht_12dm`, `ca_ht_12dm_a1` (double courbe)                │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge brute                            │ `marge_brute` (barres + ligne)                               │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de marge                          │ `taux_marge` (nombre)                                        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux generique                         │ `taux_generique` (jauge, objectif 80%)                       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Valeur stock PA                        │ `valeur_stock_pa` (nombre)                                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Ratio stock/CA                         │ `ratio_stock_ca_annuel_pct` (nombre)                         │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Produits dormants                      │ `nb_dormants_6m`, `pct_dormants_6m`, `valeur_stock_dormant`  │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D2 — Evolution CA

**Collection** : Direction Generale | **Table** : `mart_kpi_ca_evolution` | **Filtres** : pharmacie

Le titulaire doit savoir si son CA progresse ou regresse par rapport a l'an dernier. Ce dashboard repond a : "Dois-je investir, embaucher, ou reduire les couts ?" La courbe 12DM lisse la saisonnalite pour montrer la tendance de fond.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA mensuel N vs N-1                    │ `mois`, `ca_ht`, `ca_ht_a1` (double courbe)                  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Evolution YoY par mois                 │ `mois`, `evolution_ca_ht_vs_a1` (barres + %)                 │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA YTD cumule N vs N-1                 │ `ca_ht_ytd`, `ca_ht_ytd_a1` (aire)                           │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA 12DM (tendance lissee)              │ `ca_ht_12dm` (courbe)                                        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Jours de vente par mois                │ `mois`, `nb_jours_vente` (barres)                            │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D3 — Tresorerie

**Collection** : Direction Generale | **Tables** : `mart_kpi_tresorerie` + `fact_tresorerie` | **Filtres** : pharmacie, mois

Le cash-flow est le nerf de la guerre. Ce dashboard repond a : "Comment rentre l'argent ?" Si le tiers payant represente 70%, la pharmacie depend de la Secu. Si les especes baissent, signal de changement de clientele. Le titulaire utilise ce dashboard pour negocier ses frais bancaires CB et anticiper ses besoins en tresorerie.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA total mensuel                       │ `ca_total` (nombre)                                          │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Panier moyen                           │ `panier_moyen` (nombre)                                      │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb factures                            │ `nb_factures` (nombre)                                       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Repartition paiements                  │ `pct_cb`, `pct_especes`, `pct_cheques`, `pct_tiers_payant`,  │
  │                                        │ `pct_virement` (camembert)                                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge remb. vs non-remb.               │ `marge_remboursable`, `marge_non_remboursable` (barres emp.) │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Retrocessions                          │ `ca_retrocessions` (courbe)                                  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Points fidelite                        │ `points_fidelite` (nombre)                                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Remises totales                        │ `remises_totales` (nombre)                                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ TVA par taux                           │ `tva_taux1` a `tva_taux5` (tableau, fact_tresorerie)         │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D4 — Marge détaillée

**Collection** : Ventes & Performance | **Tables** : `mart_kpi_marge` + `dim_produit` + `dim_pharmacie` | **Filtres** : pharmacie, produit, date, univers

La marge est la rentabilité réelle — le CA seul ne veut rien dire si on vend à perte. Ce dashboard identifie les produits "vaches à lait" (marge élevée + volume) et les "pièges" (marges négatives). Le responsable achats utilise ces données pour renégocier les prix d'achat.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge brute par jour                   │ `date_jour`, `marge_brute` (courbe)                          │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Top 20 produits par marge              │ JOIN `dim_produit.PRD_NOM`, `marge_brute` (barres horiz.)    │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de marge par univers              │ JOIN `dim_produit.univers`, `taux_marge` (camembert)         │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Distribution taux de marge             │ `taux_marge` (histogramme)                                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marges négatives (alertes)             │ `PRD_NOM`, `taux_marge`, `marge_brute` WHERE < 0 (tableau)   │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D5 — Performance vendeurs

**Collection** : Ventes & Performance | **Table** : `mart_kpi_operateur` | **Filtres** : pharmacie, mois, operateur

Chaque vendeur a un profil different — certains vendent du volume (ordonnances), d'autres du conseil (parapharmacie a forte marge). Ce dashboard identifie les forces de chacun pour optimiser le planning, distribuer les primes, et cibler les formations.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA par operateur                       │ `operateur`, `ca_ttc` (barres horizontales)                  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Panier moyen / operateur               │ `operateur`, `panier_moyen` (barres horizontales)            │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de marge / operateur              │ `operateur`, `taux_marge` (barres)                           │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ % lignes remboursables                 │ `operateur`, `pct_lignes_remboursables` (barres)             │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Clients/jour                           │ `operateur`, `nb_clients_par_jour` (tableau)                 │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Heure de pic CA                        │ `operateur`, `heure_pic_ca` (tableau)                        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Productivite (CA moyen/jour)           │ `operateur`, `ca_moyen_par_jour` (nombre)                    │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D6 — Univers RX/OTC/PARA

**Collection** : Ventes & Performance | **Table** : `mart_kpi_univers` | **Filtres** : pharmacie, mois

La pharmacie a 3 metiers : medicaments sur ordonnance (RX), medicaments conseil (OTC), parapharmacie (PARA). Le mix determine la strategie : une pharmacie 80% RX depend de la Secu, une pharmacie 40% PARA a plus de marge mais plus de concurrence (internet). Ce dashboard guide l'amenagement de l'officine et le choix des gammes.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA par univers                         │ `univers`, `ca_ht` (camembert)                               │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Mix CA (% par univers)                 │ `pct_ca_univers` par `univers` (barres empilees 100%)        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de marge / univers                │ `univers`, `taux_marge` (barres)                             │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Mix marge (% par univers)              │ `pct_marge_univers` (camembert)                              │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Evolution vs A-1                       │ `univers`, `evolution_ca_vs_a1`, `nb_laboratoires` (tableau) │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D7 — Stock & rotation

**Collection** : Achats & Stock | **Tables** : `mart_kpi_stock` + `mart_kpi_stock_valorisation` + `dim_produit` | **Filtres** : pharmacie, mois, produit

Le stock est le plus gros poste de depense d'une pharmacie (~200-400k EUR). Un stock qui tourne vite = capital libere. Un stock qui dort = argent perdu. Ce dashboard permet de dimensionner les commandes : "J'ai 45 jours de couverture, je ne commande pas. J'ai 3 jours, commande urgente."

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Rotation stock mensuelle               │ `mois`, `rotation_stock` (courbe)                            │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Stock moyen vs ventes                  │ `stock_moyen`, `quantite_vendue` (barres groupees)           │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Couverture en jours                    │ `couverture_stock_jours` (jauge, cible 15-30j)               │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Valorisation PA vs PV                  │ `valeur_stock_pa_fin_mois`, `valeur_stock_pv_fin_mois`       │
  │                                        │ (barres empilees)                                            │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de rupture stock                  │ `taux_rupture_stock` (courbe)                                │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge latente moyenne                  │ `marge_latente_moyenne` (nombre)                             │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Variation prix achat (inflation)       │ `variation_prix_achat` WHERE != 0 (tableau alertes)          │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D8 — Ruptures & CA perdu

**Collection** : Achats & Stock | **Tables** : `mart_kpi_ruptures` + `dim_produit` | **Filtres** : pharmacie, mois, produit

Une rupture de stock = un client qui repart sans son medicament. C'est du CA perdu et de la fidelite detruite. Ce dashboard chiffre le manque a gagner en euros pour justifier des investissements en stock de securite. Le top 10 indique les produits a ne jamais laisser tomber a zero.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA estime perdu / mois                 │ `mois`, `ca_estime_perdu` (barres)                           │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge estimee perdue                   │ `mois`, `marge_estimee_perdue` (courbe)                      │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Clients impactes / mois                │ `mois`, `nb_clients_impactes` (courbe)                       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Top 10 produits en rupture             │ JOIN `PRD_NOM`, `nb_boites_manquantes` (barres horiz.)       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux de rupture demande                │ `taux_rupture_demande` (ligne)                               │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Jours de rupture / produit             │ `PRD_NOM`, `mois`, `nb_jours_rupture` (heatmap)              │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D9 — Ecoulement (sell-through)

**Collection** : Achats & Stock | **Tables** : `mart_kpi_ecoulement` + `dim_produit` + `dim_fournisseur` | **Filtres** : pharmacie, mois, fournisseur

Si j'achete 100 boites et j'en vends 40, mon taux d'ecoulement est 40% — je sur-commande. Ce dashboard identifie les fournisseurs qui "poussent" du volume et les produits sur-stockes. Le responsable achats ajuste ses quantites commandees pour liberer du capital.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux d'ecoulement mensuel              │ `mois`, `taux_ecoulement` (courbe)                           │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Produits sur-stockes (taux < 50%)      │ `PRD_NOM`, `quantite_commandee`, `quantite_vendue`,          │
  │                                        │ `taux_ecoulement` WHERE < 50% (tableau)                      │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Commande vs vendu                      │ `quantite_commandee`, `quantite_vendue` (barres groupees)    │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Ecoulement / fournisseur               │ JOIN `FOU_NOM`, AVG(`taux_ecoulement`) (barres horiz.)       │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D10 — Remises fournisseurs

**Collection** : Achats & Stock | **Tables** : `mart_kpi_remise_labo` + `dim_fournisseur` | **Filtres** : pharmacie, mois, fournisseur

Les remises fournisseurs representent un levier de marge considerable. Ce dashboard compare la remise "catalogue" (simple) vs la remise "reelle" (ponderee par le volume achete). Si un labo baisse ses remises vs A-1, c'est un signal de renegociation ou de changement de fournisseur.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Remise ponderee / labo                 │ `FOU_NOM`, `remise_ponderee_montant` (barres horiz.)         │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ PDM achats / labo                      │ `FOU_NOM`, `pdm_achats_labo` (camembert)                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Remise simple vs ponderee              │ `remise_moyenne`, `remise_ponderee_qte` (scatter plot)       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Evolution remise vs A-1                │ `FOU_NOM`, `remise_ponderee_montant`,                        │
  │                                        │ `evolution_remise_vs_a1`, `montant_total` (tableau)          │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D11 — Produits dormants

**Collection** : Achats & Stock | **Tables** : `mart_kpi_dormant` + `dim_fournisseur` | **Filtres** : pharmacie, statut_dormant, univers, fournisseur

Un produit dormant = du capital immobilisé qui ne génère aucun revenu. Ce dashboard déclenche un plan d'action concret : retourner au fournisseur, brader, ou passer en perte. Le top 20 par valeur priorise les actions à fort impact financier.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Question                               │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Capital immobilisé (dormants 6m)       │ SUM(`valeur_stock_pa`) WHERE `is_dormant_6m` (nombre)        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb produits dormants 6m                │ COUNT WHERE `is_dormant_6m` (nombre)                         │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge latente bloquée                  │ SUM(`marge_latente_bloquee`) WHERE `is_dormant_6m` (nombre)  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Répartition par statut dormant         │ `statut_dormant`, COUNT (camembert)                          │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Dormants par univers                   │ `univers`, COUNT WHERE `is_dormant_6m` (barres)              │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Top 20 dormants par valeur             │ `PRD_NOM`, `FOU_NOM`, `quantite_stock`,                      │
  │                                        │ `valeur_stock_pa`, `jours_sans_vente` (tableau)              │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

  Filtres dashboard : Pharmacie, Statut dormant, Univers, Fournisseur — reliés à toutes les questions.

#### D12 — Classification ABC (Pareto)

**Collection** : Qualite & Pilotage | **Tables** : `mart_kpi_abc` + `dim_produit` | **Filtres** : pharmacie, mois

Le principe de Pareto applique a la pharmacie : 20% des produits font 80% du CA. Les produits "A" ne doivent jamais etre en rupture (stock de securite eleve). Les produits "C" peuvent etre dereferences si dormants. Ce dashboard guide la strategie de referencement et d'approvisionnement.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb produits A / B / C                  │ `classe_abc`, COUNT (3 x nombre)                             │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Courbe de Pareto                       │ `rang`, `pct_ca_cumule` (ligne + aire)                       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA par classe ABC                      │ `classe_abc`, SUM(`ca_ht`) (barres)                          │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Repartition A / B / C                  │ `classe_abc`, COUNT (camembert)                              │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Top 10 produits A                      │ `rang`, `PRD_NOM`, `ca_ht`, `pct_ca`, `pct_ca_cumule`        │
  │                                        │ (tableau)                                                    │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D13 — Generiques & labos

**Collection** : Qualite & Pilotage | **Tables** : `mart_kpi_generique` + `dim_fournisseur` | **Filtres** : pharmacie, mois, fournisseur, univers

L'objectif CPAM de 80% de generiques est un imperatif reglementaire — en dessous, la pharmacie risque des penalites financieres. Ce dashboard suit la conformite et identifie les opportunites : substituer un princeps par un generique = meilleure marge + conformite.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux generique                         │ `taux_generique_pharmacie` (jauge, objectif 80%)             │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA generique vs princeps               │ `is_generique`, `ca_ht` (barres empilees)                    │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ PDM par labo (top 15)                  │ `FOU_NOM`, `pdm_labo` (barres horizontales)                  │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge generique vs princeps            │ `is_generique`, `taux_marge` (barres)                        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb produits / labo                     │ `FOU_NOM`, `nb_produits` (barres)                            │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Evolution CA / labo vs A-1             │ `FOU_NOM`, `ca_ht`, `ca_ht_a1`, `evolution_ca_vs_a1`,        │
  │                                        │ `marge_brute`, `evolution_marge_vs_a1` (tableau)             │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D14 — Qualite des donnees

**Collection** : Qualite & Pilotage | **Table** : `mart_kpi_qualite_donnees` | **Filtres** : aucun (vue globale)

Un dashboard qui affiche des chiffres faux est pire que pas de dashboard. Ce dashboard repond a : "Puis-je faire confiance aux chiffres ?" Si une pharmacie n'a pas synchronise depuis 48h, ses KPIs sont perimes. Le DSI utilise ce dashboard pour prioriser les interventions techniques.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Taux pharmacies OK                     │ `taux_pharmacies_ok` (jauge, vert > 90%)                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb pharmacies alerte                   │ `nb_pharmacies_alerte` + `nb_pharmacies_critique` (nombre)   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Nb erreurs total                       │ `nb_erreurs_total` (nombre rouge)                            │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Repartition OK / Alerte / Critique     │ `statut_fraicheur`, COUNT (camembert)                        │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Erreurs recentes                       │ `PHA_NOM`, `nb_erreurs_total`, `derniere_erreur` (tableau)   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Fraicheur / pharmacie                  │ `PHA_NOM`, `derniere_sync`, `heures_depuis_sync`,            │
  │                                        │ `statut_fraicheur` (tableau colore)                          │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D15 — Detail transactions (drill-down)

**Collection** : Detail operationnel | **Tables** : `fact_ventes` + `fact_commandes` + `dim_produit` + `dim_pharmacie` | **Filtres** : pharmacie, produit, date

Quand un chiffre semble anormal sur un dashboard strategique, le data analyst descend ici pour investiguer transaction par transaction. C'est le "microscope" — pas pour la direction, mais pour comprendre le "pourquoi" derriere un KPI qui derape.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Ventes par jour                        │ `date_vente`, SUM(`ca_ht`) (courbe)                          │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Top produits vendus                    │ JOIN `PRD_NOM`, SUM(`quantite_vendue`) (barres horiz.)       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Commandes / fournisseur                │ JOIN `FOU_NOM`, SUM(`montant_pahtnet`) (barres horiz.)       │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ CA par tranche d'age                   │ `ORD_CLIENT_AGE_MONTHS`, `ca_ttc` (barres)                   │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Ventes par sexe                        │ `ORD_CLIENT_SEX`, SUM(`ca_ttc`) (camembert)                  │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### D16 — Prix & mouvements stock

**Collection** : Detail operationnel | **Tables** : `fact_prix_journalier` + `fact_stock_mouvement` + `dim_produit` | **Filtres** : pharmacie, produit, date

L'inflation des prix d'achat grignote la marge sans que personne ne s'en rende compte. Ce dashboard traque l'évolution du prix d'achat produit par produit et les mouvements physiques du stock. Le responsable achats détecte les hausses silencieuses pour renégocier avant que la marge ne s'effondre.

  ┌────────────────────────────────────────┬──────────────────────────────────────────────────────────────┐
  │ Carte                                  │ Colonnes                                                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Evolution prix produit                 │ `date_prix`, `prix_tarif`, `prix_public`, `prix_achat_net`   │
  │                                        │ (multi-courbe)                                               │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Marge brute unitaire                   │ `date_prix`, `marge_brute_unitaire` (courbe)                 │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Mouvements stock / jour                │ `date_mouvement`, `delta_stock` (barres +/-)                 │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Niveau stock apres mouvement           │ `date_mouvement`, `stock_apres` (courbe)                     │
  ├────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
  │ Type d'operation                       │ `type_operation`, COUNT (camembert)                          │
  └────────────────────────────────────────┴──────────────────────────────────────────────────────────────┘

#### Couverture 26/26 tables MARTS

  ┌────────────────────────────────┬──────────────────────────────────────────────┐
  │ Table                          │ Dashboard(s)                                 │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ dim_pharmacie                  │ Tous (filtre pharmacie)                      │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ dim_produit                    │ D4, D7, D8, D9, D12, D15, D16                │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ dim_fournisseur                │ D9, D10, D11, D13                            │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_ventes                    │ D15                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_commandes                 │ D15                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_ruptures                  │ D8 (via KPI)                                 │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_stock_mouvement           │ D16                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_stock_valorisation        │ D7 (via KPI)                                 │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_tresorerie                │ D3                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_operateur                 │ D5 (via KPI)                                 │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ fact_prix_journalier           │ D16                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_marge                 │ D4                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_ecoulement            │ D9                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_abc                   │ D12                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_ruptures              │ D8                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_stock                 │ D7                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_stock_valorisation    │ D7                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_ca_evolution          │ D2                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_operateur             │ D5                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_generique             │ D13                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_univers               │ D6                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_dormant               │ D11                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_remise_labo           │ D10                                          │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_tresorerie            │ D3                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_synthese_pharmacie    │ D1                                           │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ mart_kpi_qualite_donnees       │ D14                                          │
  └────────────────────────────────┴──────────────────────────────────────────────┘

#### Création dans Metabase

1. Créer les 5 collections (menu `+` > Nouvelle collection)
2. Pour chaque dashboard : `+` > Nouveau dashboard > choisir la collection
3. Pour chaque carte : `+` dans le dashboard > Nouvelle question > table > colonnes/filtres/visualisation > Sauvegarder
4. Ajouter des filtres dashboard (date, pharmacie) qui s'appliquent à toutes les cartes
5. Les dashboards persistent dans le volume PostgreSQL (`metabase_data`)

[↑ Retour au sommaire](#table-des-matières)

---

## Voir aussi

- [Stratégie d'orchestration batch](04_strategie_orchestration_batch.md) — détail des fréquences, phases et mode nuit
- [Procédure de rollback](08_procedure_rollback.md) — restauration prod via Time Travel
- [Disaster Recovery](11_disaster_recovery.md) — plan de reprise complet (sinistres majeurs)
