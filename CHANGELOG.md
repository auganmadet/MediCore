# Changelog MediCore

Historique des évolutions du pipeline de données MediCore.
Chaque entrée décrit **ce qui a changé** du point de vue métier et son impact.

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
