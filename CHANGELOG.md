# Changelog MediCore

Historique des évolutions du pipeline de données MediCore.
Chaque entrée décrit **ce qui a changé** du point de vue métier et son impact.

---

## [2026-03-24] — Tests singular, démasquage PII, CI complète

### Ajouts
- **16 singular tests dbt** (couche 3) : vérifient les KPIs calculés sur 21 modèles MARTS (trésorerie, marge, écoulement, ruptures, stock, ABC, opérateur, univers, dormant, synthèse, 6 agrégés, PII).
- **CI pytest complète** : les 6 fichiers test unitaires sont exécutés (avant : seulement test_audit.py).
- **Post-hook seed** : raw_history renomme DATE → "Date" pour compatibilité casse mixte MySQL.
- **Documentation AUDIT** : tests par environnement documentés dans workflow_multi_env.md.

### Corrections
- **mart_kpi_stock.sql** : fichier tronqué corrigé (`v.m` → `v.mois`), détecté par les singular tests.
- **Vues AUDIT dynamiques** : `MEDICORE_PROD.AUDIT` remplacé par `{{ target.database }}.AUDIT` dans les 3 vues et la macro persist_dbt_results.
- **Tables AUDIT Snowflake** : recréées avec le schéma correct (DDL_TABLES.sql, pas DDL_WH.sql).
- **DDL_WH.sql** : tables AUDIT en doublon supprimées (source de vérité = DDL_TABLES.sql).

### Modifications
- **Démasquage PII** : PHA_NOM (raison sociale), ORD_OPERATEUR (besoin D5 Performance vendeurs), FOU_NOM (déjà fait). Seule FOU_ADRESSE reste masquée.
- **CI vues AUDIT exclues** du dbt run sur MEDICORE_TEST (tables AUDIT absentes, documenté).
- **14 tables référence corrigées** dans CLAUDE.md (5 tables inexistantes retirées).

---

## [2026-03-20] — Multi-environnement et provisionnement utilisateurs

### Ajouts
- **Multi-environnement Snowflake** : 3 databases (MEDICORE_PROD, MEDICORE_DEV, MEDICORE_TEST) avec rôles dédiés (DEV_EXECUTOR, TEST_EXECUTOR). Développement isolé de la production.
- **Seeds dbt** : 8 fichiers CSV de fixtures (pharmacie, produits, fournisseurs, factures, commandes, orders, ean13, lppr) pour tests d'intégration CI sur MEDICORE_TEST.
- **CI intégration dbt** : job `integration-dbt` dans GitHub Actions (dbt seed + run + test sur MEDICORE_TEST).
- **Provisionnement utilisateurs Metabase** : script idempotent `provision_metabase_users.py` + CSV + gouvernance collections Admin/Service + SMTP Google Workspace.
- **Documentation** : guide provisionnement (config SMTP, mot de passe d'application Google, pare-feu, IP fixe), workflow multi-env (AUDIT, SNAPSHOTS, clone DEV).

### Modifications
- **Renommage database** : MEDIcore → MEDICORE_PROD (13 fichiers mis à jour : DDL, scripts, pipelines, dbt macros/audit, docs).
- **Docker** : port Metabase exposé `0.0.0.0:3000` (réseau local), SMTP Gmail configuré.
- **Profiles.yml** : 3 targets avec database en dur (dev → MEDICORE_DEV, test → MEDICORE_TEST, prod → MEDICORE_PROD).
- **DDL_WH.sql** : création des 3 databases + rôles multi-env dans le setup initial.
- **bulk_load.py** : STAGE_NAME dynamique via `SNOWFLAKE_DATABASE` env var.

### Corrections
- **DDL_TABLES.sql** : références MEDICORE. → MEDICORE_PROD. pour cohérence avec le renommage.

---

## [2026-03-16] — Modèles dbt agrégés et qualité Metabase

### Ajouts
- **6 modèles dbt agrégés** : `mart_kpi_marge_par_produit`, `mart_kpi_marge_par_univers`, `mart_kpi_ruptures_par_produit`, `mart_kpi_ecoulement_par_fournisseur`, `mart_kpi_ventes_par_produit`, `mart_kpi_generique_marge` — pré-calculent les KPIs à granularité dashboard pour éliminer les JOIN et recalculs dans Metabase.
- **Descriptions et infobulles** : 97 cartes, 16 dashboards et 5 collections enrichis avec noms accentués et descriptions en français.
- **Filtre Univers sur D4** (Marge détaillée) : cascadé depuis Pharmacie.

### Corrections
- **FOU_NOM démasqué** : les noms de laboratoires (entreprises, pas PII) ne sont plus hashés dans `stg_fournisseurs` / `dim_fournisseur`.
- **TVA par taux (D3)** : colonne `TRS_DATE` corrigée en `DATE_JOUR`, SQL restructuré.
- **Répartition modes de paiement (D3)** : converti en SQL natif avec UNPIVOT pour le camembert.
- **Accents** : collections, dashboards et cartes corrigés (Synthèse, Trésorerie, Écoulement, Génériques, etc.).

### Modifications
- **Filtres cascadés** : Fournisseur, Opérateur, Univers, Statut dormant cascadent depuis Pharmacie. Mois reste en date-picker indépendant (limitation Metabase).
- **Ordre des filtres** : D5, D10, D11, D13 réordonnés (Pharmacie → filtres cascadés → Mois/Date en dernier).
- **D2 et D8** : filtre Produit retiré (pas pertinent pour les agrégats).

---

## [2026-03-13] — Filtres cascadés et documentation Metabase

### Ajouts
- **Filtres cascadés (linked filters)** : les filtres Fournisseur, Opérateur, Univers, Statut dormant et Mois sont désormais liés au filtre Pharmacie sur 14 dashboards. Sélectionner une pharmacie restreint automatiquement les valeurs proposées dans les autres filtres aux données existantes.
- **Documentation entités Metabase** (`docs/06_Dashboards.md`) : clarification des entités (collection, question/card, dashboard), différence MBQL vs SQL natif, types de visualisation, stockage PostgreSQL, export API et tableau des filtres cascadés.
- **Guide d'ouverture des accès** (`docs/06_Dashboards.md` §9) : procédure pas à pas pour donner accès aux dashboards par service (groupes, comptes, permissions collections/données, réseau, email SMTP).

---

## [2026-03-12] — Filtres dashboards Metabase

### Ajouts
- **Filtres D11 Produits dormants** : 4 filtres globaux (Pharmacie, Statut dormant, Univers, Fournisseur) reliés aux 6 questions du dashboard.
- **Guide utilisateur Metabase** (`docs/06_Dashboards.md`) : mode d'emploi complet pour créer les dashboards via l'interface web, avec D11 en exemple détaillé pas à pas.

---

## [2026-03-11] — Plan dashboards Metabase complet

### Ajouts
- **16 dashboards détaillés** : plan exhaustif avec 95 cartes couvrant 26/26 tables MARTS, organisés en 5 collections Metabase (Direction Générale, Ventes & Performance, Achats & Stock, Qualité & Pilotage, Détail opérationnel).
- **Justification stratégique** : chaque dashboard associé à une décision métier (titulaire, responsable achats, DSI).
- **Spécifications complètes** : colonnes, type de visualisation, filtres et jointures documentés pour chaque carte.

---

## [2026-03-09] — Exposition BI avec Metabase

### Ajouts
- **Metabase** : ajout de l'outil BI open-source au stack Docker pour visualiser les 15 KPIs, 8 faits et 3 dimensions du schéma MARTS sur des dashboards interactifs (`http://localhost:3000`).
- **PostgreSQL 16** : base metadata dédiée à Metabase (dashboards, questions sauvegardées, comptes utilisateurs). Persistée via volume Docker.
- **Documentation opérationnelle** : guide de configuration Snowflake dans Metabase, dashboards suggérés couvrant les 26/26 tables MARTS.

### Corrections
- **Rôle `MEDICORE_ANALYST`** : ajout des grants `SELECT` sur toutes les tables/vues MARTS (actuelles et futures) dans `DDL_TABLES.sql`. Le rôle existait avec `USAGE` uniquement — Metabase ne pouvait lire aucune donnée.

### Impact
- Overhead infra : +2.5 GB RAM (Metabase 2 GB + PostgreSQL 512 MB), +1.5 cores
- Coût Snowflake : marginal (SELECT read-only sur tables MARTS déjà matérialisées)
- Sécurité : rôle `MEDICORE_ANALYST` (lecture seule MARTS), port bindé `127.0.0.1`

---

## [2026-03-09] — Monitoring Kafka offset lag

### Ajouts
- **Détection du lag consumer Kafka** : mesure le retard (end_offset − committed_offset) par topic CDC après chaque batch. Un lag croissant signifie que le consumer ne suit pas le rythme de Debezium — problème invisible tant qu'il y a des events traités.
- **Alerting Teams sur lag élevé** : compteur `LAG_HIGH` incrémenté quand le lag dépasse `KAFKA_LAG_THRESHOLD` (défaut 10 000 records). Alerte après N échecs consécutifs + notification recovery — même pattern que le volume check `ZERO_VOL`.
- **Métriques audit Snowflake** : table `AUDIT.CDC_LAG_METRICS` (1 ligne par topic par run) pour historiser le lag et détecter les tendances.
- **Fichier métriques bash** : `/tmp/cdc_lag_metrics` au format `topic=lag` pour lecture simple dans `batch_loop.sh`.

### Corrections
- **Listener Kafka INTERNAL** : le consumer CDC et Kafdrop utilisaient le listener EXTERNAL (`kafka:9092`, annonce `localhost:9092`) au lieu du listener INTERNAL (`kafka:29092`). Corrigé dans `docker-compose.yml`, `.env` et le défaut Python.

### Impact
- Overhead ~1-2s par cycle (consumer temporaire, lecture metadata seulement, pas de rebalance)
- Tout en try/except — ne casse jamais le pipeline existant

---

## [2026-03-09] — Optimisation coûts : Marts KPI en incremental

### Modifications
- **9 marts KPI convertis en incremental** : passage de `materialized='table'` (full refresh) à `materialized='incremental'` avec stratégie `merge` sur les 2 derniers mois.
  - `mart_kpi_abc` — Classification ABC produits
  - `mart_kpi_marge` — Marge par produit/jour
  - `mart_kpi_generique` — Génériques et PDM laboratoires
  - `mart_kpi_stock` — Stock mensuel et rotation
  - `mart_kpi_ruptures` — Ruptures et CA perdu
  - `mart_kpi_remise_labo` — Remise pondérée par labo
  - `mart_kpi_operateur` — Performance vendeurs
  - `mart_kpi_tresorerie` — Trésorerie mensuelle
  - `mart_kpi_univers` — KPIs par univers (RX, OTC, PARA)

### Marts restés en table (full refresh obligatoire)
- `mart_kpi_dormant` — utilise `current_date()` (état changeant quotidiennement)
- `mart_kpi_qualite_donnees` — utilise `current_timestamp()` (fraîcheur temps réel)
- `mart_kpi_ca_evolution` — calculs YTD et 12DM rolling (historique complet requis)
- `mart_kpi_synthese_pharmacie` — agrège depuis marts non-incrémentaux

### Impact
- **Économie estimée** : ~35 EUR/mois (~420 EUR/an)
- **Réduction temps d'exécution** : 80-90% sur les runs quotidiens
- **Marts incremental** : 11/15 (73%)
- **Marts table** : 4/15 (27%)

### Recommandation
- Planifier un `--full-refresh` mensuel pour rattraper les données tardives

---

## [2026-03-06] — KPIs Dashboard-Ready et Documentation

### Ajouts
- **mart_kpi_univers** : KPIs pré-agrégés par univers (RX, OTC, PARA, HORS_REMB) pour affichage direct sur dashboard sans filtre. Inclut CA, marge, taux de marge, % CA univers, % marge univers, evolution vs A-1.
- **mart_kpi_synthese_pharmacie** : vue consolidée de tous les KPIs principaux au niveau pharmacie/mois. Inclut CA + evolution, marge + taux, valeur stock, ratio stock/CA annuel, CA générique + taux, % dormants 6m/12m. Aucun calcul requis côté application.

### Documentation
- **docs/05_KPIs.md** : ajout de 6 nouvelles sections (2.10-2.15) documentant les marts KPI avec formules, grain et utilités métier :
  - mart_kpi_ca_evolution — Evolution CA vs A-1
  - mart_kpi_generique — Génériques et Parts de Marché Labo
  - mart_kpi_remise_labo — Remise Pondérée par Laboratoire
  - mart_kpi_univers — KPIs par Univers (Dashboard)
  - mart_kpi_dormant — Produits Sans Vente
  - mart_kpi_synthese_pharmacie — Vue Dashboard Consolidée
- **docs/05_KPIs.md section 4.4** : documentation des 3 KPIs NON DISPO avec structures de données requises :
  - Cartes de fidélité (source: API Mediplace, table `mediplace.client`)
  - Montant de challenges Medila (source: API Mediplace, table `mediplace.challenge_vente`)
  - CA par catégorie de marché (source: référentiel catégories à créer)
- **KPI-recherche_Simon.csv** : mise à jour avec colonnes exactes des modèles dbt, suppression des calculs pour KPIs OK, ajout des données requises pour KPIs NON DISPO.
- **dbt/models/marts/_marts.yml** : documentation des 2 nouveaux marts avec descriptions et tags.

### Contexte métier documenté
- **PDM** (Part De Marché) : ratio CA labo / CA total, permet négociation fournisseurs et analyse concurrentielle
- **CPAM** : objectif 80% de substitution générique imposé par l'Assurance Maladie
- **Univers** : classification RX (prescription), OTC (automédication), PARA (parapharmacie), HORS_REMB
- **Remise pondérée** : moyenne pondérée par quantité ou montant (plus représentative que moyenne simple)

---

## [2026-03-03] — Présentation PowerPoint MediCore

### Ajouts
- **Présentation PowerPoint** : `docs/MediCore_Presentation.pptx` — 21 slides aux couleurs Médiprix couvrant contexte, architecture, ingestion, transformations dbt, opérations, CI/CD et feuille de route.
- **Générateur Python** : `scripts/generate_pptx.py` — génère la présentation via python-pptx avec schéma d'architecture interactif (zones, sous-groupes, logos, flèches).
- **Notes du présentateur** : speech complet sur les 21 slides, ton oral, explications des choix techniques (pourquoi Kafka, pourquoi dbt, pourquoi SCD2, pourquoi star schema…).
- **Logos technologiques** : 10 logos dans `docs/logos/` (AWS, dbt, Debezium, Kafka, Metabase, MySQL, Power BI, Python, Snowflake, Tableau).

### Nettoyage
- **Historique Git** : suppression des mentions "Generated with Cortex Code" et "Co-Authored-By: Cortex Code" dans les 14 commits concernés.

---

## [2026-02-26] — Durcissement et refactoring

### Ajouts
- **CI/CD GitHub Actions** : pipeline de validation automatique (lint Python, validation syntaxe dbt, build Docker, ShellCheck bash) + déploiement continu vers GitHub Container Registry (GHCR). L'image Docker est automatiquement publiée sur `ghcr.io/auganmadet/medicore` (tags SHA + latest) après passage des 4 jobs CI sur `main`.
- **Guide opérationnel** : documentation `docs/03_operations.md` avec architecture batch, variables d'environnement, commandes utiles et procédures de diagnostic.
- **Tests marts** : `dbt test --select tag:marts` exécuté après les tests staging dans le batch loop, avec compteur d'échecs et alertes Teams.
- **Timeout par phase** : chaque phase du batch loop est limitée par `PHASE_TIMEOUT_SEC` (défaut 30 min) pour éviter les blocages.
- **Arrêt graceful** : le batch loop intercepte SIGTERM/SIGINT et termine proprement après la phase en cours (compatible `docker compose stop`).
- **Détection stale lock** : le batch loop vérifie que le PID dans le lock file est encore actif avant de skipper l'itération.

### Modifications
- **Ports Docker** : tous les ports exposés sont maintenant bindés sur `127.0.0.1` au lieu de `0.0.0.0` (MySQL 3307, Kafka 9092, Connect 8083, Kafdrop 9000).
- **Conteneur non-root** : le Dockerfile utilise désormais un utilisateur `appuser` au lieu de `root` pour le runtime.
- **Valeurs hardcodées → variables d'environnement** : database, warehouse et rôle Snowflake sont configurables via `SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE_NAME` et `SNOWFLAKE_DBT_ROLE_NAME` (avec valeurs par défaut).
- **Type hints Python** : annotations de type ajoutées sur toutes les signatures de fonctions dans les 4 fichiers Python principaux.
- **Docstrings Google-style** : documentation des fonctions avec sections Args, Returns, Raises.
- **Exceptions spécifiques** : remplacement de `except Exception` par des exceptions ciblées (`ProgrammingError`, `RuntimeError`, `OSError`).
- **Imports** : réorganisation selon la convention stdlib → third-party → local.

### Corrections
- **CI lint Python** : suppression des imports inutilisés, correction whitespace/tabs, ajout import manquant `snowflake.connector` dans `diagnose_recover.py`.
- **CI dbt parse** : ajout de toutes les variables d'environnement Snowflake requises par `profiles.yml` (valeurs factices pour validation syntaxe uniquement).
- **Dockerfile** : correction du warning `FromAsCasing` (`as` → `AS` pour cohérence avec `FROM`).

### Nettoyage
- Suppression de `pipelines/utils/pii_masking.py` (code mort, masquage assuré par dbt).
- Suppression des dépendances commentées dans `requirements.txt`.
- `diagnose_recover.py` : remplacement de tous les `print()` par `logger.info/warning/error`.

---

## [2026-02-25] — Lineage opérationnel et audit persistant

### Ajouts
- **Schéma AUDIT Snowflake** : 3 tables (`PIPELINE_RUNS`, `PIPELINE_STEP_RUNS`, `DBT_MODEL_RUNS`) pour tracer chaque itération du batch loop, chaque phase et chaque modèle dbt exécuté.
- **RUN_ID unique par batch** : chaque cycle du batch_loop génère un UUID propagé à toutes les phases (CDC, ref-reload, dbt staging/snapshot/marts/test, freshness). Permet de relier les données produites au batch qui les a générées.
- **Persistance résultats dbt** : macro `persist_dbt_results` insère automatiquement le statut, le temps d'exécution et les rows affected de chaque modèle/test dbt dans `AUDIT.DBT_MODEL_RUNS` via le hook `on-run-end`.
- **3 vues audit dbt** : `audit_run_summary` (résumé par run), `audit_dbt_summary` (résumé par invocation dbt), `audit_latest_runs` (7 derniers jours, détail step par step).
- **Column-level lineage** : descriptions enrichies dans les YAML staging et marts avec le chemin source de chaque colonne clé (ex: `source: RAW_COMMANDES.PHA_ID ← winstat.COMMANDES.PHA_ID`). Navigable via `dbt docs generate`.
- **Rétention audit 90 jours** : purge automatique quotidienne à 01h des données AUDIT de plus de 90 jours.
- **Argument `--run-id`** : `daily_cdc_batch.py` et `bulk_load.py` acceptent désormais un identifiant de run pour le suivi audit.

---

## [2026-02-24] — Fiabilité CDC + historisation

### Ajouts
- **Dead-letter queue (DLQ)** : les messages CDC malformés ou non traitables sont désormais conservés dans une table `RAW._DLQ` au lieu d'être perdus silencieusement. Permet de diagnostiquer les incidents sans perte de données.
- **Alerting volume CDC** : le pipeline détecte les batches consécutifs sans événement et alerte l'équipe via Teams. Un topic vide pendant plusieurs cycles peut indiquer un problème Debezium ou Kafka.
- **Historisation SCD2** : 3 snapshots dbt suivent les modifications des dimensions dans le temps :
  - `snap_pharmacie` — nom, code GERS, date d'installation
  - `snap_produit` — nom, code remboursement, code acte, TVA, fournisseur
  - `snap_fournisseur` — nom, type, répartiteur, adresse
  - Chaque modification est conservée avec sa date de début et de fin de validité (`dbt_valid_from` / `dbt_valid_to`).

### Corrections
- **Commit Kafka manuel** : les offsets Kafka ne sont validés qu'après insertion réussie dans Snowflake. Corrige le risque de perte de messages si le flush échoue.

---

## [2026-02-24] — CLAUDE.md et règles de développement

### Ajouts
- **CLAUDE.md** : fichier d'instructions persistantes pour Claude Code. Décrit l'architecture, les conventions, les commandes et la sécurité du projet.
- **19 règles de développement** (`.claude/rules/`) couvrant : architecture ELT, standards Python/SQL, connecteurs Snowflake/MySQL/Kafka, dbt, Docker, qualité, masquage PII, intégrité CDC, modèle pharmacie.
- **Règles issues des bugs** : 11 règles ajoutées à partir des incidents réels du projet (fuite de curseurs Snowflake, buffering MySQL, BOOLEAN Parquet, zombies Docker, metadata COPY INTO, commit Kafka manuel, DLQ obligatoire, alerting volume).

---

## [2026-02-23] — Alerting Teams, qualité dbt, nettoyage

### Ajouts
- **Tests dbt métier** : 6 tests `expression_is_true` sur les colonnes calculées des marts (marge, taux de rupture, rotation stock, taux d'écoulement, valorisation). Vérifient que les formules métier produisent des valeurs cohérentes.
- **Résumé dbt automatique** : hook `on-run-end` qui envoie un résumé Teams après chaque run dbt (nombre de warnings, erreurs, modèles exécutés).
- **Validation credentials Snowflake** : le pipeline vérifie la connexion Snowflake au démarrage et échoue immédiatement si les identifiants sont invalides, au lieu de tourner en boucle.

### Corrections
- **Timeout CDC configurable** : le délai d'attente des messages Kafka est passé de 10s à 30s (configurable via `BATCH_TIMEOUT_S`). Évite les faux positifs "pas de données" en cas de latence réseau.
- **Retry webhook Teams** : 3 tentatives avec backoff exponentiel pour les alertes Teams. Évite les alertes perdues en cas d'indisponibilité temporaire du webhook.
- **Contexte d'erreur bulk load** : les messages d'erreur du bulk load incluent désormais la phase en cours (connexion, extraction, upload, COPY INTO) pour faciliter le diagnostic.

### Nettoyage
- Suppression de 8 fichiers obsolètes (backups, vestiges, utilitaires inutilisés).
- Suppression du code commenté dans le Dockerfile.

---

## [2026-02-20] — Freshness dbt sur 18 tables

### Ajouts
- **Source freshness** : contrôle de fraîcheur dbt sur les 18 tables RAW. Seuils : CDC 12h warn / 24h error, référence 36h warn / 48h error. Le batch loop exécute `dbt source freshness` après chaque cycle et alerte Teams en cas de dépassement.

---

## [2026-02-19] — Alerting Teams, rechargement référence, clustering

### Ajouts
- **Alerting Teams** : webhook Microsoft Teams pour les alertes pipeline. Compteur d'échecs consécutifs par phase (CDC, dbt staging, dbt marts, dbt test, reference reload). Alerte après 3 échecs + notification de recovery.
- **Rechargement quotidien des 14 tables de référence** : TRUNCATE + bulk reload à 03h00, avec `FORCE = TRUE` sur COPY INTO pour contourner le cache de metadata Snowflake.
- **Clustering keys** : ajout de `CLUSTER BY` sur les tables RAW volumineuses pour accélérer les requêtes dbt.

---

## [2026-02-19] — Merge PR #1 et #2

### Merge
- Première intégration de la branche `Architecture-Medicore` dans `main`.
- Pipeline complet : CDC Debezium + Kafka + RAW + STG + MARTS fonctionnel.

---

## [2026-02-18] — PII en dbt, micro-batch, config multi-env

### Modifications
- **Masquage PII déplacé en dbt** : le masquage MD5 des données personnelles (nom, adresse, email) est désormais réalisé dans les modèles staging dbt au lieu de Python. Plus fiable et auditable.
- **Micro-batch CDC** : le consommateur Kafka traite les messages par micro-batches pour réduire la latence.
- **Configuration dev/prod** : fichier de config séparé pour les environnements de développement et de production (target dbt, timeouts, seuils).

### Corrections
- **fact_operateur** : correction des casts VARCHAR sur les colonnes numériques.
- **stg_pharmacies_erreur** : correction de la clé de déduplication.

---

## [2026-02-17] — 6 nouveaux KPIs + diagnostic

### Ajouts
- **6 nouveaux KPIs marts** :
  - `mart_kpi_stock_valorisation` — valorisation du stock et couverture en jours
  - `mart_kpi_ruptures` — impact des ruptures et CA perdu estimé
  - `mart_kpi_tresorerie` — trésorerie mensuelle par mode de paiement
  - `mart_kpi_operateur` — performance par vendeur
  - `mart_kpi_abc` — classification Pareto des produits
  - `mart_kpi_qualite_donnees` — monitoring fraîcheur et erreurs
- **4 tables de faits** : `fact_tresorerie`, `fact_stock_valorisation`, `fact_ruptures`, `fact_operateur` — les 18 tables RAW sont désormais toutes exploitées.
- **Script diagnostic** : `diagnose_recover.py` pour diagnostic automatique et reprise en cas d'incident bulk load.

---

## [2026-02-14–16] — Bulk load stabilisation

### Corrections
- **Fix OOM** : correction de la fuite mémoire lors du bulk load (920M rows chargés en 18 tables). Chunk size 500K rows, `gc.collect()` après chaque chunk.
- **FORCE=TRUE sur COPY INTO** : corrige le problème de fichiers silencieusement ignorés après un TRUNCATE (metadata Snowflake persistante 64 jours).
- **Fix CDC_TIMESTAMP** : correction des dates invalides dans les colonnes CDC timestamp.
- **Résilience réseau** : `get_mysql_conn()` encapsulé dans try/except pour gérer les déconnexions MySQL.
- **Fix connecteur Debezium** : correction d'une virgule manquante dans le JSON de configuration.

---

## [2026-02-12–13] — Bulk load initial

### Ajouts
- **Bulk load via Parquet** : chargement initial des 18 tables MySQL vers Snowflake RAW via Parquet + stage interne + COPY INTO. Remplace l'approche CSV.
- **4 tables CDC transactionnelles** : COMMANDES, FACTURES, ORDERS, MODSTOCK identifiées comme tables à forte volumétrie, traitées par CDC Debezium.

---

## [2026-02-08–11] — Pipeline CDC fonctionnel

### Ajouts
- Pipeline CDC complet : Debezium capture les changements MySQL, Kafka les transporte, le consommateur Python les insère dans Snowflake RAW.
- Couche STG dbt : déduplication par `ROW_NUMBER()`, filtrage des deletes, typage.
- Couche MARTS dbt : `fact_ventes`, `fact_commandes`, `fact_prix_journalier`, `fact_stock_mouvement` + 3 KPIs croisés (`mart_kpi_marge`, `mart_kpi_stock`, `mart_kpi_ecoulement`).
- Tests dbt staging : 3 tests passés à severity `warn` pour données manquantes en dev.

---

## [2026-01-20–22] — Fondations

### Ajouts
- **Déduplication CDC** : logique de déduplication dans les modèles staging.
- **Traitement CDC batch** : consommateur Kafka Python avec flush périodique.
- **Masquage PII** : première implémentation du masquage MD5 en Python.
- **Modèles dbt** : premiers modèles staging et marts.

### Sécurité
- Suppression des fichiers `.env` et des credentials du suivi Git.

---

## [2026-01-16] — Initialisation

### Ajouts
- Création du repository MediCore.
- Structure initiale : `pipelines/`, `dbt/`, `scripts/`, `docs/`.
- Premiers modèles dbt (staging + marts).
